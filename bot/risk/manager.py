"""Risk management: position sizing, exposure limits, circuit breakers."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from bot.market.models import PortfolioState
from bot.strategy.signal import Signal

logger = logging.getLogger(__name__)


@dataclass
class RiskCheck:
    allowed: bool
    reason: str = ""
    position_size: float = 0.0


class RiskManager:
    def __init__(
        self,
        max_position_usd: float = 100.0,
        max_exposure_usd: float = 500.0,
        max_daily_loss_usd: float = 200.0,
        kelly_fraction: float = 0.25,
        min_edge: float = 0.03,
        cooldown_seconds: float = 30.0,
        max_consecutive_losses: int = 5,
    ):
        self.max_position_usd = max_position_usd
        self.max_exposure_usd = max_exposure_usd
        self.max_daily_loss_usd = max_daily_loss_usd
        self.kelly_fraction = kelly_fraction
        self.min_edge = min_edge
        self.cooldown_seconds = cooldown_seconds
        self.max_consecutive_losses = max_consecutive_losses
        self._last_trade_time: float = 0
        self._consecutive_losses: int = 0
        self._halted: bool = False

    def check(self, signal: Signal, portfolio: PortfolioState) -> RiskCheck:
        if self._halted:
            return RiskCheck(allowed=False, reason="Trading halted by circuit breaker")

        # Edge threshold
        if signal.edge < self.min_edge:
            return RiskCheck(allowed=False, reason=f"Edge {signal.edge:.3f} < min {self.min_edge}")

        # Daily loss limit
        if portfolio.daily_pnl <= -self.max_daily_loss_usd:
            self._halted = True
            return RiskCheck(allowed=False, reason=f"Daily loss limit hit: ${portfolio.daily_pnl:.2f}")

        # Exposure limit
        if portfolio.open_exposure >= self.max_exposure_usd:
            return RiskCheck(
                allowed=False,
                reason=f"Max exposure reached: ${portfolio.open_exposure:.2f}",
            )

        # Cooldown
        now = time.time()
        if now - self._last_trade_time < self.cooldown_seconds:
            return RiskCheck(allowed=False, reason="Cooldown period active")

        # Consecutive losses
        if self._consecutive_losses >= self.max_consecutive_losses:
            return RiskCheck(
                allowed=False,
                reason=f"Max consecutive losses: {self._consecutive_losses}",
            )

        # Position sizing via quarter-Kelly
        size = self._kelly_size(signal, portfolio.balance_usd)
        if size < 1.0:
            return RiskCheck(allowed=False, reason=f"Kelly size too small (${size:.2f})")

        self._last_trade_time = now
        return RiskCheck(allowed=True, position_size=size)

    def _kelly_size(self, signal: Signal, balance: float) -> float:
        """Quarter-Kelly position sizing.

        Full Kelly: f = (p * b - q) / b
        where p = predicted_prob, q = 1-p, b = (1/market_prob - 1) = odds
        """
        p = signal.predicted_prob
        q = 1 - p
        b = (1 / signal.market_prob) - 1  # decimal odds

        if b <= 0:
            return 0.0

        kelly = (p * b - q) / b
        if kelly <= 0:
            return 0.0

        size = balance * kelly * self.kelly_fraction
        size = min(size, self.max_position_usd)
        size = min(size, balance * 0.40)  # never risk more than 40% of balance

        return round(size, 2)

    def record_outcome(self, won: bool):
        if won:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1

    def reset_daily(self):
        self._halted = False

    def force_halt(self):
        self._halted = True

    def resume(self):
        self._halted = False
        self._consecutive_losses = 0
