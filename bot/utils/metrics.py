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
        self._historical = self._load_history()

    def _load_history(self) -> list[dict]:
        """Load all trades from the JSONL log file."""
        trades = []
        if self.log_file.exists():
            for line in self.log_file.read_text().strip().splitlines():
                try:
                    trades.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return trades

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
        self._historical.append(entry)

    def _stats(self) -> tuple[int, int]:
        """Return (total_trades, wins) from historical log."""
        total = len(self._historical)
        wins = sum(1 for t in self._historical if t.get("outcome") == "win")
        return total, wins

    def summary(self, portfolio: PortfolioState) -> str:
        total, wins = self._stats()
        elapsed = time.time() - self._session_start
        win_rate = wins / total if total else 0.0

        lines = [
            f"Session: {elapsed / 3600:.1f}h",
            f"Trades: {total} ({wins}W / {total - wins}L)",
            f"Win rate: {win_rate:.1%}",
            f"PnL: ${portfolio.total_pnl:+.2f}",
            f"Balance: ${portfolio.balance_usd:.2f}",
            f"Open positions: {len(portfolio.open_positions)}",
        ]
        return " | ".join(lines)

    def format_telegram(self, portfolio: PortfolioState) -> str:
        total, wins = self._stats()
        win_rate = wins / total if total else 0.0

        return (
            f"📊 <b>Bot Status</b>\n"
            f"Balance: <code>${portfolio.balance_usd:.2f}</code>\n"
            f"Trades: {total} ({wins}W/{total - wins}L)\n"
            f"Win rate: {win_rate:.1%}\n"
            f"Daily PnL: <code>${portfolio.daily_pnl:+.2f}</code>\n"
            f"Total PnL: <code>${portfolio.total_pnl:+.2f}</code>\n"
            f"Open: {len(portfolio.open_positions)} positions "
            f"(${portfolio.open_exposure:.2f})"
        )
