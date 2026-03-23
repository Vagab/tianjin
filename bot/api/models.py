"""Pydantic response models for the API."""

from __future__ import annotations

from pydantic import BaseModel


class PortfolioResponse(BaseModel):
    balance_usd: float
    daily_pnl: float
    total_pnl: float
    open_exposure: float
    open_positions: int
    win_rate: float


class TradeResponse(BaseModel):
    id: int
    uid: str
    timestamp: float
    market_slug: str
    direction: str
    amount_usd: float
    entry_price: float
    edge: float
    outcome: str | None
    pnl: float


class TradesListResponse(BaseModel):
    trades: list[TradeResponse]
    total: int
    limit: int
    offset: int


class TradeStatsResponse(BaseModel):
    total: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_edge: float
    avg_pnl: float


class StatusResponse(BaseModel):
    running: bool
    halted: bool
    paper_trading: bool
    current_market: str | None
    market_end_ts: float | None
    uptime_seconds: float


class RiskResponse(BaseModel):
    max_position_usd: float
    max_exposure_usd: float
    max_daily_loss_usd: float
    kelly_fraction: float
    min_edge: float
    consecutive_losses: int
    halted: bool


class MarketResponse(BaseModel):
    slug: str
    question: str
    up_price: float
    down_price: float
    start_ts: int
    end_ts: int
    active: bool


class PriceTickResponse(BaseModel):
    timestamp: float
    price: float
    volume: float


class EquitySnapshotResponse(BaseModel):
    timestamp: float
    balance_usd: float
    daily_pnl: float
    total_pnl: float
    open_exposure: float
