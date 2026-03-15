"""Trade tracking and performance metrics."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from bot.market.models import PortfolioState, TradeRecord

logger = logging.getLogger(__name__)


class MetricsTracker:
    def __init__(self, log_file: str = "trades.jsonl"):
        self.log_file = Path(log_file)
        self._session_start = time.time()

    def log_trade(self, trade: TradeRecord):
        entry = {
            "timestamp": trade.timestamp,
            "market": trade.market_slug,
            "direction": trade.direction.value,
            "amount": trade.amount_usd,
            "entry_price": trade.entry_price,
            "edge": trade.edge,
            "outcome": trade.outcome,
            "pnl": trade.pnl,
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def summary(self, portfolio: PortfolioState) -> str:
        settled = [t for t in portfolio.trades if t.outcome is not None]
        total = len(settled)
        wins = sum(1 for t in settled if t.outcome == "win")
        total_pnl = sum(t.pnl for t in settled)
        elapsed = time.time() - self._session_start

        lines = [
            f"Session: {elapsed / 3600:.1f}h",
            f"Trades: {total} ({wins}W / {total - wins}L)",
            f"Win rate: {portfolio.win_rate:.1%}",
            f"PnL: ${total_pnl:+.2f}",
            f"Balance: ${portfolio.balance_usd:.2f}",
            f"Open positions: {len(portfolio.open_positions)}",
        ]
        return " | ".join(lines)

    def format_telegram(self, portfolio: PortfolioState) -> str:
        settled = [t for t in portfolio.trades if t.outcome is not None]
        total = len(settled)
        wins = sum(1 for t in settled if t.outcome == "win")

        return (
            f"📊 <b>Bot Status</b>\n"
            f"Balance: <code>${portfolio.balance_usd:.2f}</code>\n"
            f"Trades: {total} ({wins}W/{total - wins}L)\n"
            f"Win rate: {portfolio.win_rate:.1%}\n"
            f"Daily PnL: <code>${portfolio.daily_pnl:+.2f}</code>\n"
            f"Total PnL: <code>${portfolio.total_pnl:+.2f}</code>\n"
            f"Open: {len(portfolio.open_positions)} positions "
            f"(${portfolio.open_exposure:.2f})"
        )
