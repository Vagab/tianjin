"""Signal dataclass — output of strategy evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from bot.market.models import Direction


@dataclass
class Signal:
    direction: Direction
    confidence: float  # 0.0 to 1.0
    predicted_prob: float  # our estimate of true probability
    market_prob: float  # current Polymarket implied probability
    edge: float  # predicted_prob - market_prob - fee
    timestamp: float = 0.0

    @property
    def is_actionable(self) -> bool:
        return self.edge > 0 and self.confidence > 0.5
