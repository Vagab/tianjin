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


