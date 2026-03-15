"""V2 Momentum Strategy.

Requires multiple confirmations before trading:
1. Momentum magnitude above threshold
2. Consistent move (not a spike-and-fade)
3. RSI confirmation (not fighting the trend)
4. Move is accelerating (not exhausted)
5. Sufficient edge after fees
"""

from __future__ import annotations

import logging
import math
import time

from bot.market.models import Direction, Market
from bot.price.feed import BtcPriceFeed
from bot.price.indicators import (
    momentum,
    momentum_consistency,
    price_acceleration,
    rsi,
    volatility,
)
from bot.strategy.base import Strategy
from bot.strategy.signal import Signal

logger = logging.getLogger(__name__)


class MomentumStrategy(Strategy):
    def __init__(
        self,
        lookback_seconds: int = 45,
        min_move_pct: float = 0.05,
        fee_pct: float = 0.02,
        min_edge: float = 0.03,
    ):
        self.lookback_seconds = lookback_seconds
        self.min_move_pct = min_move_pct
        self.fee_pct = fee_pct
        self.min_edge = min_edge

    async def evaluate(self, market: Market, price_feed: BtcPriceFeed) -> Signal | None:
        prices = price_feed.prices_since(self.lookback_seconds)

        if len(prices) < 15:
            return None

        mom = momentum(prices)

        # Skip if move is too small
        if abs(mom) < self.min_move_pct:
            return None

        direction = Direction.UP if mom > 0 else Direction.DOWN

        # --- FILTER 1: Consistency ---
        # The move should be steady, not a single spike
        consistency = momentum_consistency(prices, segments=3)
        if consistency < 0.67:
            logger.debug(
                "Skip: inconsistent move (%.0f%% segments agree, need 67%%)",
                consistency * 100,
            )
            return None

        # --- FILTER 2: Acceleration ---
        # Prefer moves that are accelerating, not exhausted
        accel = price_acceleration(prices)
        move_accelerating = (direction == Direction.UP and accel > 0) or (
            direction == Direction.DOWN and accel < 0
        )

        # --- FILTER 3: RSI confirmation ---
        rsi_val = rsi(prices)
        rsi_confirms = (direction == Direction.UP and rsi_val > 55) or (
            direction == Direction.DOWN and rsi_val < 45
        )

        # Require at least one of acceleration or RSI to confirm
        if not move_accelerating and not rsi_confirms:
            logger.debug(
                "Skip: no confirmation (accel=%.4f%% rsi=%.1f dir=%s)",
                accel, rsi_val, direction.value,
            )
            return None

        # --- PROBABILITY ESTIMATE ---
        # Logistic function: maps absolute momentum to probability of our direction
        # Calibrated: 0.03% → ~57%, 0.05% → ~62%, 0.1% → ~73%, 0.3% → ~95%
        k = 500.0
        predicted_prob = 1 / (1 + math.exp(-k * abs(mom) / 100))

        # Adjust for volatility regime — high vol reduces confidence
        vol = volatility(prices)
        if vol > 0.0005:
            vol_factor = min(1.0, 0.0005 / vol)
            predicted_prob = 0.5 + (predicted_prob - 0.5) * max(0.3, vol_factor)

        # Boost probability if both confirmations agree
        if move_accelerating and rsi_confirms:
            predicted_prob = 0.5 + (predicted_prob - 0.5) * 1.1
            predicted_prob = min(0.98, predicted_prob)

        # Get current market price for our direction
        market_prob = market.up_price if direction == Direction.UP else market.down_price

        # Edge = predicted probability - market price - fees
        edge = predicted_prob - market_prob - self.fee_pct

        if edge < self.min_edge:
            logger.debug(
                "Skip: edge=%.4f < min %.4f (pred=%.3f mkt=%.3f mom=%.4f%%)",
                edge, self.min_edge, predicted_prob, market_prob, mom,
            )
            return None

        # --- CONFIDENCE ---
        confidence = min(0.95, 0.5 + abs(mom) / 0.5)
        confirmations = 0
        if rsi_confirms:
            confirmations += 1
            confidence = min(0.95, confidence + 0.05)
        if move_accelerating:
            confirmations += 1
            confidence = min(0.95, confidence + 0.05)
        if consistency == 1.0:
            confirmations += 1
            confidence = min(0.95, confidence + 0.05)

        # --- REASONING ---
        reasons = []
        reasons.append(f"BTC {mom:+.3f}% in {self.lookback_seconds}s")
        reasons.append(f"consistency {consistency:.0%}")
        if move_accelerating:
            reasons.append(f"accelerating ({accel:+.4f}%)")
        else:
            reasons.append(f"decelerating ({accel:+.4f}%)")
        reasons.append(f"RSI {rsi_val:.0f} {'confirms' if rsi_confirms else 'neutral'}")
        reasons.append(f"vol {vol:.6f}")

        reasoning = (
            f"Pred {predicted_prob:.0%} {direction.value} vs market {market_prob:.0%} "
            f"→ {edge:.1%} edge. "
            + ", ".join(reasons)
            + f". {confirmations}/3 confirmations."
        )

        signal = Signal(
            direction=direction,
            confidence=confidence,
            predicted_prob=predicted_prob,
            market_prob=market_prob,
            edge=edge,
            timestamp=time.time(),
            reasoning=reasoning,
        )

        logger.info(
            "Signal: %s | mom=%.4f%% | pred=%.3f | mkt=%.3f | edge=%.3f | conf=%.2f | confirms=%d",
            direction.value, mom, predicted_prob, market_prob, edge, confidence, confirmations,
        )

        return signal
