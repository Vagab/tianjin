"""Lightweight technical indicators computed over price lists and tick data."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.price.feed import PriceTick


def momentum(prices: list[float]) -> float:
    """Price change as percentage from first to last."""
    if len(prices) < 2:
        return 0.0
    return (prices[-1] - prices[0]) / prices[0] * 100



def rsi(prices: list[float], period: int = 14) -> float:
    """Relative Strength Index (0-100)."""
    if len(prices) < period + 1:
        return 50.0  # neutral default

    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def volatility(prices: list[float]) -> float:
    """Standard deviation of returns."""
    if len(prices) < 3:
        return 0.0
    returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]
    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    return math.sqrt(variance)


def ema(prices: list[float], period: int = 10) -> float:
    """Exponential Moving Average of the last `period` prices."""
    if not prices:
        return 0.0
    k = 2 / (period + 1)
    value = prices[0]
    for p in prices[1:]:
        value = p * k + value * (1 - k)
    return value


def momentum_consistency(prices: list[float], segments: int = 3) -> float:
    """Fraction of sub-segments that agree on direction with the overall move.

    Returns 0.0-1.0. Higher = move is steady, not a spike-and-fade.
    """
    if len(prices) < segments * 2:
        return 0.0
    overall = prices[-1] - prices[0]
    if overall == 0:
        return 0.0
    seg_len = len(prices) // segments
    agree = 0
    for i in range(segments):
        start = i * seg_len
        end = start + seg_len if i < segments - 1 else len(prices)
        seg_move = prices[end - 1] - prices[start]
        if (seg_move > 0) == (overall > 0):
            agree += 1
    return agree / segments


def price_acceleration(prices: list[float]) -> float:
    """Is the move accelerating or decelerating?

    Returns > 0 if second half moved more than first half (accelerating).
    """
    if len(prices) < 4:
        return 0.0
    mid = len(prices) // 2
    first_half = (prices[mid] - prices[0]) / prices[0] * 100
    second_half = (prices[-1] - prices[mid]) / prices[mid] * 100
    return second_half - first_half


def trade_flow_imbalance(ticks: list[PriceTick]) -> float:
    """Trade Flow Imbalance: (buy_vol - sell_vol) / total_vol.

    Range: -1 (all selling) to +1 (all buying).
    Binance: m=False → buyer was aggressor (buy), m=True → seller was aggressor (sell).
    """
    if not ticks:
        return 0.0
    buy_vol = sum(t.volume for t in ticks if not t.is_buyer_maker)
    sell_vol = sum(t.volume for t in ticks if t.is_buyer_maker)
    total = buy_vol + sell_vol
    if total == 0:
        return 0.0
    return (buy_vol - sell_vol) / total


def price_slope(prices: list[float]) -> float:
    """Linear regression slope of prices, normalized as % per sample.

    More robust than simple start-to-end momentum — resistant to end-point noise.
    """
    n = len(prices)
    if n < 3:
        return 0.0
    mean_x = (n - 1) / 2
    mean_y = sum(prices) / n
    num = sum((i - mean_x) * (p - mean_y) for i, p in enumerate(prices))
    den = sum((i - mean_x) ** 2 for i in range(n))
    if den == 0 or mean_y == 0:
        return 0.0
    slope = num / den
    return slope / mean_y * 100  # as percentage


def tick_intensity(ticks: list[PriceTick], seconds: float = 10) -> float:
    """Ratio of recent tick rate to overall tick rate.

    > 1.0 means activity is accelerating recently.
    """
    if len(ticks) < 10:
        return 1.0
    total_span = ticks[-1].timestamp - ticks[0].timestamp
    if total_span <= 0:
        return 1.0

    cutoff = ticks[-1].timestamp - seconds
    recent = [t for t in ticks if t.timestamp >= cutoff]
    recent_span = seconds

    overall_rate = len(ticks) / total_span
    recent_rate = len(recent) / recent_span if recent_span > 0 else 0

    return recent_rate / overall_rate if overall_rate > 0 else 1.0


def vwap(ticks: list[PriceTick]) -> float:
    """Volume-Weighted Average Price."""
    if not ticks:
        return 0.0
    total_pv = sum(t.price * t.volume for t in ticks)
    total_vol = sum(t.volume for t in ticks)
    if total_vol == 0:
        return ticks[-1].price
    return total_pv / total_vol


def vwap_deviation(ticks: list[PriceTick]) -> float:
    """(current_price - vwap) / vwap * 100.

    Positive = price above fair value, negative = below.
    """
    if not ticks:
        return 0.0
    v = vwap(ticks)
    if v == 0:
        return 0.0
    return (ticks[-1].price - v) / v * 100

