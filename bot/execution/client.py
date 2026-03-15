"""Live Polymarket order execution via py-clob-client."""

from __future__ import annotations

import logging

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BalanceAllowanceParams, OrderArgs, OrderType

from bot.execution.paper import Executor, OrderResult
from bot.market.models import Direction, Market, PortfolioState, Position, TradeRecord

logger = logging.getLogger(__name__)


class LiveExecutor(Executor):
    def __init__(self, host: str, private_key: str, chain_id: int = 137, funder: str = ""):
        self._is_proxy = bool(funder)
        kwargs = {
            "host": host,
            "key": private_key,
            "chain_id": chain_id,
        }
        if funder:
            kwargs["funder"] = funder
            kwargs["signature_type"] = 1

        self._client = ClobClient(**kwargs)
        self._init_creds()
        self.portfolio = PortfolioState()

    def _init_creds(self):
        creds = self._client.create_or_derive_api_creds()
        self._client.set_api_creds(creds)
        logger.info("Polymarket API credentials initialized")

    async def get_balance(self) -> float:
        sig_type = 1 if self._is_proxy else 0
        params = BalanceAllowanceParams(asset_type="COLLATERAL", signature_type=sig_type)
        result = self._client.get_balance_allowance(params)
        # Balance is in USDC micro-units (6 decimals)
        raw = float(result.get("balance", "0"))
        balance = raw / 1e6
        self.portfolio.balance_usd = balance
        return balance

    async def execute(self, market: Market, direction: Direction, amount_usd: float) -> OrderResult:
        token_id = (
            market.up_token.token_id if direction == Direction.UP
            else market.down_token.token_id
        )

        if not token_id:
            logger.error("No token ID for direction %s", direction.value)
            return OrderResult(success=False, error="Missing token ID")

        try:
            # Use limit order at current market price for better fill rates
            # (FOK market orders fail on thin books)
            price = market.up_price if direction == Direction.UP else market.down_price
            size = round(amount_usd / price, 2)  # shares = USD / price_per_share

            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side="BUY",
            )
            signed_order = self._client.create_order(order_args)
            resp = self._client.post_order(signed_order, OrderType.GTC)

            success = resp.get("success", False) if isinstance(resp, dict) else bool(resp)

            logger.info(
                "Order %s: %s $%.2f on %s | resp=%s",
                "FILLED" if success else "FAILED",
                direction.value,
                amount_usd,
                market.slug,
                resp,
            )

            fill_price = market.up_price if direction == Direction.UP else market.down_price
            order_id = resp.get("orderID", "") if isinstance(resp, dict) else ""

            if success:
                import time
                self.portfolio.trades.append(TradeRecord(
                    market_slug=market.slug,
                    direction=direction,
                    amount_usd=amount_usd,
                    entry_price=fill_price,
                    edge=0.0,
                    timestamp=time.time(),
                ))
                self.portfolio.open_positions.append(Position(
                    market_slug=market.slug,
                    direction=direction,
                    amount_usd=amount_usd,
                    entry_price=fill_price,
                    token_id=token_id,
                ))

            return OrderResult(
                success=success,
                order_id=order_id,
                fill_price=fill_price,
            )

        except Exception as e:
            logger.error("Order execution failed: %s", e)
            return OrderResult(success=False, error=str(e))

    def settle_position(self, market_slug: str, winning_direction: Direction):
        """Settle a position based on market outcome."""
        remaining = []
        for pos in self.portfolio.open_positions:
            if pos.market_slug != market_slug:
                remaining.append(pos)
                continue

            if pos.direction == winning_direction:
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

            logger.info(
                "[LIVE] Settled %s: %s PnL=$%.2f",
                market_slug, outcome.upper(), pnl,
            )

        self.portfolio.open_positions = remaining

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
