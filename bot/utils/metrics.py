"""Trade tracking and performance metrics."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.db import Database
    from bot.market.models import PortfolioState

logger = logging.getLogger(__name__)


class MetricsTracker:
    def __init__(self, db: Database):
        self.db = db
        self._session_start = time.time()

    async def log_trade_from_values(
        self,
        timestamp: float,
        market_slug: str,
        direction: str,
        amount_usd: float,
        entry_price: float,
        edge: float = 0.0,
        outcome: str | None = None,
        pnl: float = 0.0,
        order_id: str | None = None,
    ):
        """Log a trade to the database."""
        await self.db.insert_trade(
            timestamp=timestamp,
            market_slug=market_slug,
            direction=direction,
            amount_usd=amount_usd,
            entry_price=entry_price,
            edge=edge,
            outcome=outcome,
            pnl=pnl,
            order_id=order_id,
        )

    async def summary(self, portfolio: PortfolioState) -> str:
        stats = await self.db.get_trade_stats()
        total = stats["total"]
        wins = stats["wins"]
        elapsed = time.time() - self._session_start
        win_rate = stats["win_rate"]

        lines = [
            f"Session: {elapsed / 3600:.1f}h",
            f"Trades: {total} ({wins}W / {total - wins}L)",
            f"Win rate: {win_rate:.1%}",
            f"PnL: ${portfolio.total_pnl:+.2f}",
            f"Balance: ${portfolio.balance_usd:.2f}",
            f"Open positions: {len(portfolio.open_positions)}",
        ]
        return " | ".join(lines)

    async def format_telegram(self, portfolio: PortfolioState) -> str:
        stats = await self.db.get_trade_stats()
        total = stats["total"]
        wins = stats["wins"]
        win_rate = stats["win_rate"]

        return (
            f"<b>Bot Status</b>\n"
            f"Balance: <code>${portfolio.balance_usd:.2f}</code>\n"
            f"Trades: {total} ({wins}W/{total - wins}L)\n"
            f"Win rate: {win_rate:.1%}\n"
            f"Daily PnL: <code>${portfolio.daily_pnl:+.2f}</code>\n"
            f"Total PnL: <code>${portfolio.total_pnl:+.2f}</code>\n"
            f"Open: {len(portfolio.open_positions)} positions "
            f"(${portfolio.open_exposure:.2f})"
        )
