"""Main event loop: discover → monitor → evaluate → execute → settle → repeat."""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
from pathlib import Path

from config.settings import settings
from bot.market.discovery import MarketDiscovery
from bot.market.models import Direction, Market
from bot.price.feed import BtcPriceFeed
from bot.strategy.momentum import MomentumStrategy
from bot.execution.paper import PaperExecutor
from bot.execution.client import LiveExecutor
from bot.risk.manager import RiskManager
from bot.telegram.bot import TelegramNotifier
from bot.utils.logging import setup_logging
from bot.utils.metrics import MetricsTracker

logger = logging.getLogger(__name__)


class TradingBot:
    def __init__(self):
        self.discovery = MarketDiscovery(interval_seconds=settings.interval_seconds)
        self.price_feed = BtcPriceFeed(ws_url=settings.binance_ws_url)
        self.strategy = MomentumStrategy(
            lookback_seconds=settings.momentum_lookback_seconds,
            min_move_pct=settings.momentum_min_move_pct,
            fee_pct=settings.estimated_taker_fee_pct,
            min_edge=settings.min_edge,
        )
        self.risk = RiskManager(
            max_position_usd=settings.max_position_usd,
            max_exposure_usd=settings.max_exposure_usd,
            max_daily_loss_usd=settings.max_daily_loss_usd,
            kelly_fraction=settings.kelly_fraction,
            min_edge=settings.min_edge,
        )
        self.metrics = MetricsTracker()
        self.telegram = TelegramNotifier(
            token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )

        if settings.paper_trading:
            self.executor = PaperExecutor(initial_balance=1000.0)
            logger.info("Running in PAPER trading mode")
        else:
            pk = settings.polymarket_private_key.get_secret_value()
            if not pk:
                raise ValueError("POLYMARKET_PRIVATE_KEY required for live trading")
            self.executor = LiveExecutor(
                host=settings.polymarket_host,
                private_key=pk,
                chain_id=settings.polymarket_chain_id,
                funder=settings.polymarket_funder,
            )
            logger.info("Running in LIVE trading mode")

        self._running = False
        self._last_daily_reset: float = 0
        self._state_file = Path(__file__).resolve().parent.parent / "bot_state.json"
        self._traded_file = Path(__file__).resolve().parent.parent / "traded_markets.json"
        self._traded_markets: set[str] = self._load_traded_markets()

    async def start(self):
        self._running = True

        # Start subsystems
        await self.price_feed.start()
        await self.price_feed.wait_for_price()
        logger.info("BTC price feed active: $%.2f", self.price_feed.current_price)

        # Wire up Telegram
        portfolio_getter = lambda: (
            self.executor.portfolio if hasattr(self.executor, "portfolio") else None
        )
        self.telegram.set_dependencies(
            portfolio_getter=portfolio_getter,
            metrics=self.metrics,
            risk_manager=self.risk,
            stop_callback=self.stop,
            balance_refresher=self._refresh_balance,
        )
        await self.telegram.start()

        balance = await self.executor.get_balance()
        self._load_or_init_state(balance)
        logger.info("Starting balance: $%.2f (initial: $%.2f)", balance, self._initial_balance)

        # Main loop
        try:
            await self._run_loop()
        except asyncio.CancelledError:
            logger.info("Bot cancelled")
        finally:
            await self._shutdown()

    def stop(self):
        self._running = False

    def _load_or_init_state(self, current_balance: float):
        """Load persisted state (initial balance, daily start) or initialize."""
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        try:
            data = json.loads(self._state_file.read_text())
            self._initial_balance = data["initial_balance"]
            if data.get("daily_date") == today:
                self._daily_start_balance = data["daily_start_balance"]
            else:
                self._daily_start_balance = current_balance
                data["daily_start_balance"] = current_balance
                data["daily_date"] = today
                self._state_file.write_text(json.dumps(data))
            # Prevent daily reset from re-triggering on restart
            self._last_daily_reset = datetime.datetime.now(datetime.timezone.utc).date().toordinal()
            logger.info("Loaded state: initial=$%.2f daily_start=$%.2f", self._initial_balance, self._daily_start_balance)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            self._initial_balance = current_balance
            self._daily_start_balance = current_balance
            self._last_daily_reset = datetime.datetime.now(datetime.timezone.utc).date().toordinal()
            self._save_state()
            logger.info("Initialized state: balance=$%.2f", current_balance)

    def _load_traded_markets(self) -> set[str]:
        """Load set of market slugs we've already traded (survives restarts)."""
        try:
            data = json.loads(self._traded_file.read_text())
            return set(data.get("markets", []))
        except (FileNotFoundError, json.JSONDecodeError):
            return set()

    def _mark_traded(self, market_slug: str):
        """Record that we've traded this market window."""
        self._traded_markets.add(market_slug)
        # Keep only the last 20 to avoid unbounded growth
        if len(self._traded_markets) > 20:
            self._traded_markets = set(list(self._traded_markets)[-20:])
        self._traded_file.write_text(json.dumps({"markets": list(self._traded_markets)}))

    def _save_state(self):
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        self._state_file.write_text(json.dumps({
            "initial_balance": self._initial_balance,
            "daily_start_balance": self._daily_start_balance,
            "daily_date": today,
        }))

    def _sync_pnl(self):
        """Update portfolio PnL from actual balance difference."""
        bal = self.executor.portfolio.balance_usd
        self.executor.portfolio.total_pnl = bal - self._initial_balance
        self.executor.portfolio.daily_pnl = bal - self._daily_start_balance

    async def _refresh_balance(self):
        """Refresh balance from Polymarket and sync PnL."""
        await self.executor.get_balance()
        self._sync_pnl()

    async def _shutdown(self):
        logger.info("Shutting down...")
        await self.price_feed.stop()
        await self.telegram.stop()
        await self.discovery.close()

        if hasattr(self.executor, "portfolio"):
            logger.info("Final: %s", self.metrics.summary(self.executor.portfolio))

    async def _run_loop(self):
        while self._running:
            # Reset daily stats at midnight UTC
            import datetime
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            today_key = now_utc.date().toordinal()
            if today_key != self._last_daily_reset:
                self._last_daily_reset = today_key
                self.risk.reset_daily()
                self._daily_start_balance = self.executor.portfolio.balance_usd
                self._save_state()
                self._sync_pnl()
                logger.info("Daily reset (daily_start=$%.2f)", self._daily_start_balance)

            try:
                await self._run_window()
            except Exception as e:
                logger.error("Window error: %s", e, exc_info=True)
                await self.telegram.notify_error(str(e))
                await asyncio.sleep(10)

    async def _run_window(self):
        # 1. DISCOVER current market
        market = await self.discovery.get_current_market()
        if not market:
            logger.warning("No active market found, waiting...")
            await asyncio.sleep(30)
            return

        # Skip markets we've already traded (prevents duplicates on restart)
        if market.slug in self._traded_markets:
            logger.info("Already traded %s, skipping to next window", market.slug)
            remaining = market.end_ts - time.time()
            if remaining > 0:
                await asyncio.sleep(remaining + 2)
            return

        # Capture BTC price at window open — this is what the contract settles on
        window_open_btc_price = self.price_feed.price_at(float(market.start_ts))
        if window_open_btc_price is None:
            window_open_btc_price = self.price_feed.current_price

        logger.info(
            "Market: %s | Up=%.3f Down=%.3f | BTC open=$%.2f",
            market.slug, market.up_price, market.down_price, window_open_btc_price,
        )

        # Calculate time remaining in this window
        now = time.time()
        window_end = market.end_ts
        remaining = window_end - now

        if remaining < 30:
            # Too close to end, wait for next window
            logger.info("Window ending in %.0fs, waiting for next...", remaining)
            await asyncio.sleep(remaining + 2)
            return

        # 2. EVALUATE — check for signal every second during first 2 minutes
        traded = False
        trade_btc_price: float | None = None  # BTC price at time of trade
        current_order_id: str | None = None  # track open order for cancel+replace
        current_direction: Direction | None = None
        eval_duration = min(120, remaining - 30)  # stop 30s before end
        eval_end = now + eval_duration

        last_refresh = 0.0
        while time.time() < eval_end and self._running and not traded:
            # Refresh market prices every 15 seconds (not every tick)
            now_t = time.time()
            if now_t - last_refresh > 15:
                fresh_market = await self.discovery.get_current_market()
                if fresh_market:
                    market = fresh_market
                last_refresh = now_t

            signal = await self.strategy.evaluate(market, self.price_feed, window_open_btc_price)

            if signal and signal.is_actionable:
                # If we have an open order in the opposite direction, cancel it first
                if current_order_id and current_direction and signal.direction != current_direction:
                    logger.info(
                        "Signal flipped %s → %s, cancelling order %s",
                        current_direction.value, signal.direction.value, current_order_id,
                    )
                    if hasattr(self.executor, "cancel_order"):
                        self.executor.cancel_order(current_order_id)
                    current_order_id = None
                    current_direction = None

                # Skip if we already have an order in this direction
                if current_order_id and current_direction == signal.direction:
                    await asyncio.sleep(1)
                    continue

                # 3. RISK CHECK
                portfolio = self.executor.portfolio
                risk_check = self.risk.check(signal, portfolio)

                if risk_check.allowed:
                    # 4. EXECUTE
                    result = await self.executor.execute(
                        market, signal.direction, risk_check.position_size,
                        edge=signal.edge,
                    )

                    if result.success:
                        traded = True
                        self._mark_traded(market.slug)
                        current_order_id = result.order_id
                        current_direction = signal.direction
                        trade_btc_price = self.price_feed.current_price
                        # Sync balance and PnL from Polymarket
                        await self.executor.get_balance()
                        self._sync_pnl()
                        logger.info(
                            "Trade executed: %s $%.2f | edge=%.3f | BTC=$%.2f",
                            signal.direction.value,
                            risk_check.position_size,
                            signal.edge,
                            trade_btc_price,
                        )
                        await self.telegram.notify_trade(
                            direction=signal.direction.value,
                            amount=risk_check.position_size,
                            edge=signal.edge,
                            market=market.slug,
                            reasoning=signal.reasoning,
                        )
                    else:
                        # Order might have gone through despite exception.
                        # Track it so we don't place a contradicting order.
                        current_order_id = result.order_id or "unknown"
                        current_direction = signal.direction
                        logger.warning("Order failed: %s — won't retry this direction", result.error)
                else:
                    logger.debug("Risk blocked: %s", risk_check.reason)

            await asyncio.sleep(1)

        # 5. WAIT for window to end
        remaining = market.end_ts - time.time()
        if remaining > 0:
            logger.info("Waiting %.0fs for window to close...", remaining)
            await asyncio.sleep(remaining + 5)  # extra 5s for settlement

        # 6. SETTLE — check outcome
        if traded:
            await self._settle(market, window_open_btc_price)

    async def _settle(self, market: Market, window_open_price: float | None):
        """Check outcome and settle position."""
        try:
            # Determine winner: compare BTC price at window open vs window close
            # This matches how Polymarket settles the binary contract
            end_price = self.price_feed.current_price

            if window_open_price is None or end_price == 0:
                window_open_price = self.price_feed.price_at(float(market.start_ts))
                if window_open_price is None:
                    logger.error("Cannot determine outcome — no price data")
                    return

            winning = Direction.UP if end_price >= window_open_price else Direction.DOWN

            logger.info(
                "Settlement: BTC $%.2f (open) -> $%.2f (close) = %s",
                window_open_price, end_price, winning.value,
            )

            # Settle via executor (works for both paper and live)
            self.executor.settle_position(market.slug, winning)

            # Always refresh balance and PnL from Polymarket
            await self.executor.get_balance()
            self._sync_pnl()

            # Record outcome in risk manager
            won = any(
                t.outcome == "win"
                for t in self.executor.portfolio.trades
                if t.market_slug == market.slug
            )
            self.risk.record_outcome(won)

            # Notify via Telegram and log
            for trade in reversed(self.executor.portfolio.trades):
                if trade.market_slug == market.slug and trade.outcome:
                    await self.telegram.notify_outcome(
                        market=market.slug,
                        outcome=trade.outcome,
                        pnl=trade.pnl,
                        balance=self.executor.portfolio.balance_usd,
                    )
                    self.metrics.log_trade(trade)
                    break

            logger.info(
                "Summary: %s",
                self.metrics.summary(self.executor.portfolio),
            )

        except Exception as e:
            logger.error("Settlement error: %s", e)


def main():
    setup_logging()
    bot = TradingBot()

    loop = asyncio.new_event_loop()

    def handle_signal(sig, frame):
        logger.info("Received signal %s, stopping...", sig)
        bot.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        loop.run_until_complete(bot.start())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
