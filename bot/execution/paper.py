"""Paper trading executor — simulates trades without real orders."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from bot.market.models import Direction, Market, Position, PortfolioState, TradeRecord

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    success: bool
    order_id: str = ""
    fill_price: float = 0.0
    error: str = ""


class Executor(ABC):
    @abstractmethod
    async def get_balance(self) -> float: ...

    @abstractmethod
    async def execute(self, market: Market, direction: Direction, amount_usd: float, edge: float = 0.0) -> OrderResult: ...


class PaperExecutor(Executor):
    def __init__(self, initial_balance: float = 1000.0):
        self.portfolio = PortfolioState(balance_usd=initial_balance)

    async def get_balance(self) -> float:
        return self.portfolio.balance_usd

    async def execute(self, market: Market, direction: Direction, amount_usd: float) -> OrderResult:
        if amount_usd > self.portfolio.balance_usd:
            return OrderResult(success=False, error="Insufficient balance")

        price = market.up_price if direction == Direction.UP else market.down_price
        token_id = (
            market.up_token.token_id if direction == Direction.UP
            else market.down_token.token_id
        )

        # Deduct from balance
        self.portfolio.balance_usd -= amount_usd

        # Create position
        position = Position(
            market_slug=market.slug,
            direction=direction,
            amount_usd=amount_usd,
            entry_price=price,
            token_id=token_id,
        )
        self.portfolio.open_positions.append(position)

        # Record trade
        trade = TradeRecord(
            market_slug=market.slug,
            direction=direction,
            amount_usd=amount_usd,
            entry_price=price,
            edge=0.0,
            timestamp=time.time(),
        )
        self.portfolio.trades.append(trade)

        logger.info(
            "[PAPER] %s $%.2f on %s at %.4f",
            direction.value, amount_usd, market.slug, price,
        )

        return OrderResult(success=True, order_id=f"paper-{int(time.time())}", fill_price=price)

    def settle_position(self, market_slug: str, winning_direction: Direction):
        """Settle a position based on market outcome."""
        remaining = []
        for pos in self.portfolio.open_positions:
            if pos.market_slug != market_slug:
                remaining.append(pos)
                continue

            if pos.direction == winning_direction:
                # Win: receive $1 per share, shares = amount / entry_price
                shares = pos.amount_usd / pos.entry_price
                payout = shares  # each share pays $1
                pnl = payout - pos.amount_usd
                outcome = "win"
            else:
                pnl = -pos.amount_usd
                outcome = "loss"

            self.portfolio.balance_usd += pos.amount_usd + pnl
            self.portfolio.daily_pnl += pnl
            self.portfolio.total_pnl += pnl

            # Update trade record
            for trade in self.portfolio.trades:
                if trade.market_slug == market_slug and trade.outcome is None:
                    trade.outcome = outcome
                    trade.pnl = pnl
                    break

            logger.info(
                "[PAPER] Settled %s: %s PnL=$%.2f | Balance=$%.2f",
                market_slug, outcome.upper(), pnl, self.portfolio.balance_usd,
            )

        self.portfolio.open_positions = remaining
