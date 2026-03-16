from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass
class PriceTick:
    price: float
    timestamp: float
    volume: float = 0.0
    is_buyer_maker: bool = False  # True = seller aggressor, False = buyer aggressor


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


@dataclass
class Token:
    token_id: str
    outcome: str  # "Up" or "Down"
    price: float = 0.0


@dataclass
class Market:
    slug: str
    condition_id: str
    question: str
    up_token: Token
    down_token: Token
    start_ts: int
    end_ts: int
    active: bool = True

    @property
    def up_price(self) -> float:
        return self.up_token.price

    @property
    def down_price(self) -> float:
        return self.down_token.price


@dataclass
class Signal:
    direction: Direction
    confidence: float  # 0.0 to 1.0
    predicted_prob: float
    market_prob: float
    edge: float  # predicted_prob - market_prob - fee
    timestamp: float = 0.0


@dataclass
class TradeRecord:
    market_slug: str
    direction: Direction
    amount_usd: float
    entry_price: float
    edge: float
    timestamp: float
    outcome: str | None = None  # "win" / "loss" / None (pending)
    pnl: float = 0.0


@dataclass
class Position:
    market_slug: str
    direction: Direction
    amount_usd: float
    entry_price: float
    token_id: str


@dataclass
class PortfolioState:
    balance_usd: float = 1000.0
    open_positions: list[Position] = field(default_factory=list)
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    trades: list[TradeRecord] = field(default_factory=list)

    @property
    def open_exposure(self) -> float:
        return sum(p.amount_usd for p in self.open_positions)

    @property
    def win_rate(self) -> float:
        settled = [t for t in self.trades if t.outcome is not None]
        if not settled:
            return 0.0
        wins = sum(1 for t in settled if t.outcome == "win")
        return wins / len(settled)
