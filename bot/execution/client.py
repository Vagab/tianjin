"""Live Polymarket order execution via py-clob-client."""

from __future__ import annotations

import logging
import time

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BalanceAllowanceParams, OrderArgs, OrderType

from bot.execution.paper import Executor, OrderResult
from bot.execution.redeemer import Redeemer
from bot.market.models import Direction, Market, PortfolioState, Position, TradeRecord
from bot.price.polymarket_feed import UserFeed

logger = logging.getLogger(__name__)


class LiveExecutor(Executor):
    def __init__(
        self,
        host: str,
        private_key: str,
        chain_id: int = 137,
        funder: str = "",
        rpc_url: str = "",
        builder_api_key: str = "",
        builder_secret: str = "",
        builder_passphrase: str = "",
        fill_timeout: float = 30.0,
    ):
        self._is_proxy = bool(funder)
        self._fill_timeout = fill_timeout
        kwargs = {
            "host": host,
            "key": private_key,
            "chain_id": chain_id,
        }
        if funder:
            kwargs["funder"] = funder
            kwargs["signature_type"] = 1

        self._client = ClobClient(**kwargs)
        self._api_creds = self._init_creds()
        self.portfolio = PortfolioState()

        # UserFeed for fill confirmation via WebSocket
        if self._api_creds:
            self._user_feed = UserFeed(
                api_key=self._api_creds.api_key,
                secret=self._api_creds.api_secret,
                passphrase=self._api_creds.api_passphrase,
            )
        else:
            self._user_feed = None
            logger.warning("No API creds for UserFeed — fill confirmation disabled")

        # Gasless redeemer via Polymarket relayer
        self._redeemer = None
        if builder_api_key and builder_secret and builder_passphrase:
            try:
                self._redeemer = Redeemer(
                    private_key=private_key,
                    funder=funder,
                    builder_api_key=builder_api_key,
                    builder_secret=builder_secret,
                    builder_passphrase=builder_passphrase,
                )
                logger.info("Redeemer initialized (gasless via relayer)")
            except Exception as e:
                logger.warning("Failed to init redeemer: %s", e)

    def _init_creds(self) -> dict:
        creds = self._client.create_or_derive_api_creds()
        self._client.set_api_creds(creds)
        logger.info("Polymarket API credentials initialized")
        return creds

    async def start_feeds(self):
        """Start the UserFeed WebSocket for fill confirmation."""
        if self._user_feed:
            await self._user_feed.start()
            logger.info("UserFeed started for fill confirmation")

    async def stop_feeds(self):
        """Stop the UserFeed WebSocket."""
        if self._user_feed:
            await self._user_feed.stop()

    async def get_balance(self) -> float:
        sig_type = 1 if self._is_proxy else 0
        params = BalanceAllowanceParams(asset_type="COLLATERAL", signature_type=sig_type)
        result = self._client.get_balance_allowance(params)
        raw = float(result.get("balance", "0"))
        balance = raw / 1e6
        self.portfolio.balance_usd = balance
        return balance

    async def execute(self, market: Market, direction: Direction, amount_usd: float, edge: float = 0.0) -> OrderResult:
        token_id = (
            market.up_token.token_id if direction == Direction.UP
            else market.down_token.token_id
        )

        if not token_id:
            logger.error("No token ID for direction %s", direction.value)
            return OrderResult(success=False, error="Missing token ID")

        try:
            base_price = market.up_price if direction == Direction.UP else market.down_price
            price = min(round(base_price + 0.02, 2), 0.99)
            size = round(amount_usd / price, 2)

            if size < 5:
                size = 5.0
                amount_usd = size * price

            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side="BUY",
            )
            signed_order = self._client.create_order(order_args)
            resp = self._client.post_order(signed_order, OrderType.GTC)

            success = resp.get("success", False) if isinstance(resp, dict) else bool(resp)
            order_id = resp.get("orderID", "") if isinstance(resp, dict) else ""

            logger.info(
                "Order posted: %s $%.2f on %s | order_id=%s | resp=%s",
                direction.value, amount_usd, market.slug, order_id[:16] if order_id else "?", resp,
            )

            if not success:
                return OrderResult(success=False, order_id=order_id, error="post_order failed")

            # Determine fill price and amount
            fill_price = price
            actual_amount = amount_usd
            resp_status = resp.get("status", "") if isinstance(resp, dict) else ""

            if resp_status == "matched":
                # API already confirmed fill — extract actual amounts
                taking = float(resp.get("takingAmount", "0")) / 1e6
                making = float(resp.get("makingAmount", "0"))
                if taking > 0 and making > 0:
                    fill_price = taking / making
                    actual_amount = taking
                logger.info("Fill confirmed via API: %s price=%.4f amount=$%.2f",
                            direction.value, fill_price, actual_amount)
            elif self._user_feed and order_id:
                # Wait for fill confirmation via UserFeed WebSocket
                fill = await self._user_feed.wait_for_fill(order_id, timeout=self._fill_timeout)
                if fill.filled:
                    fill_price = fill.fill_price if fill.fill_price > 0 else price
                    actual_amount = fill.fill_size * fill_price if fill.fill_size > 0 else amount_usd
                    logger.info(
                        "Fill confirmed via WS: %s price=%.3f size=%.2f status=%s",
                        direction.value, fill_price, fill.fill_size, fill.status,
                    )
                else:
                    logger.warning(
                        "Order not filled (status=%s), cancelling %s",
                        fill.status, order_id[:16],
                    )
                    self.cancel_order(order_id)
                    return OrderResult(success=False, order_id=order_id, error=f"Fill {fill.status}")

            self.portfolio.trades.append(TradeRecord(
                market_slug=market.slug,
                direction=direction,
                amount_usd=actual_amount,
                entry_price=fill_price,
                edge=edge,
                timestamp=time.time(),
            ))
            self.portfolio.open_positions.append(Position(
                market_slug=market.slug,
                direction=direction,
                amount_usd=actual_amount,
                entry_price=fill_price,
                token_id=token_id,
            ))

            return OrderResult(
                success=True,
                order_id=order_id,
                fill_price=fill_price,
            )

        except Exception as e:
            logger.error("Order execution failed: %s", e)
            return OrderResult(success=False, error=str(e))

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns True if cancelled."""
        if not order_id:
            return False
        try:
            resp = self._client.cancel(order_id)
            cancelled = bool(resp) if not isinstance(resp, dict) else resp.get("canceled", False)
            logger.info("Cancel order %s: %s", order_id, resp)
            return cancelled
        except Exception as e:
            logger.error("Cancel failed for %s: %s", order_id, e)
            return False

    def settle_position(
        self,
        market_slug: str,
        winning_direction: Direction | None = None,
        winning_token_id: str = "",
    ):
        """Settle a position based on market outcome.

        Uses winning_token_id (authoritative) if provided,
        falls back to winning_direction comparison.
        """
        remaining = []
        for pos in self.portfolio.open_positions:
            if pos.market_slug != market_slug:
                remaining.append(pos)
                continue

            if winning_token_id and pos.token_id:
                won = pos.token_id == winning_token_id
            elif winning_direction is not None:
                won = pos.direction == winning_direction
            else:
                logger.error("settle_position called without direction or token_id")
                remaining.append(pos)
                continue

            if won:
                shares = pos.amount_usd / pos.entry_price
                payout = shares
                pnl = payout - pos.amount_usd
                outcome = "win"
            else:
                pnl = -pos.amount_usd
                outcome = "loss"

            self.portfolio.daily_pnl += pnl
            self.portfolio.total_pnl += pnl

            for trade in self.portfolio.trades:
                if trade.market_slug == market_slug and trade.outcome is None:
                    trade.outcome = outcome
                    trade.pnl = pnl
                    break

            method = "token_id" if (winning_token_id and pos.token_id) else "direction"
            logger.info(
                "[LIVE] Settled %s: %s PnL=$%.2f (via %s)",
                market_slug, outcome.upper(), pnl, method,
            )

        self.portfolio.open_positions = remaining

    def redeem_all(self) -> list[dict]:
        """Redeem all winning positions via gasless relayer."""
        if not self._redeemer:
            return []
        return self._redeemer.redeem_all()

    async def get_market_price(self, market: Market, direction: Direction) -> float:
        token_id = (
            market.up_token.token_id if direction == Direction.UP
            else market.down_token.token_id
        )
        try:
            price = self._client.get_price(token_id, "buy")
            return float(price) if price else 0.5
        except Exception:
            return market.up_price if direction == Direction.UP else market.down_price
