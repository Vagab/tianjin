"""Lightweight technical indicators computed over price lists."""

from __future__ import annotations

import math


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

