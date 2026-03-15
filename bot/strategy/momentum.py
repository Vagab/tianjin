"""V3 Momentum + Order Flow Strategy.

Signal flow:
1. Momentum magnitude check (hard gate)
2. Logistic with k=200 → base predicted_prob
3. Consistency → soft dampener on predicted_prob
4. TFI (Trade Flow Imbalance) → boost or dampen/kill
5. VWAP deviation → mean-reversion guard
6. Volatility dampening
7. RSI + acceleration → minor confidence adjustments
8. Edge check against market price + fees
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
    trade_flow_imbalance,
    volatility,
    vwap_deviation,
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
        ticks = price_feed.ticks_since(self.lookback_seconds)

        if len(prices) < 15:
            return None

        mom = momentum(prices)

        # --- HARD GATE: minimum move ---
        if abs(mom) < self.min_move_pct:
            return None

        direction = Direction.UP if mom > 0 else Direction.DOWN

        # --- BASE PROBABILITY ---
        # k=200: 0.03%→~53%, 0.05%→~55%, 0.1%→~60%, 0.3%→~73%
        # More conservative than k=500, lets TFI/VWAP do the heavy lifting
        k = 200.0
        predicted_prob = 1 / (1 + math.exp(-k * abs(mom) / 100))

        # --- CONSISTENCY (soft dampener, not hard gate) ---
        consistency = momentum_consistency(prices, segments=3)
        # Scale: 0.33 → dampen to 33% of edge, 0.67 → 67%, 1.0 → full
        predicted_prob = 0.5 + (predicted_prob - 0.5) * max(0.33, consistency)

        # --- TFI: Trade Flow Imbalance (primary confirmation) ---
        tfi = trade_flow_imbalance(ticks)
        tfi_aligned = (direction == Direction.UP and tfi > 0) or (
            direction == Direction.DOWN and tfi < 0
        )
        tfi_opposing = (direction == Direction.UP and tfi < -0.2) or (
            direction == Direction.DOWN and tfi > 0.2
        )

        # TFI opposing the move = flow doesn't support the price action → kill
        if tfi_opposing:
            logger.debug(
                "Skip: TFI %.2f opposes %s move (mom=%.4f%%)",
                tfi, direction.value, mom,
            )
            return None

        # TFI aligned boosts probability proportionally
        if tfi_aligned:
            tfi_boost = min(0.08, abs(tfi) * 0.1)  # max +8% boost
            predicted_prob += tfi_boost

        # --- VWAP DEVIATION (mean-reversion guard) ---
        vwap_dev = vwap_deviation(ticks)
        # Price extended in our direction → mean reversion risk, dampen
        if (direction == Direction.UP and vwap_dev > 0.2) or \
           (direction == Direction.DOWN and vwap_dev < -0.2):
            predicted_prob = 0.5 + (predicted_prob - 0.5) * 0.7
        # Price compressed against our direction → more room to run, slight boost
        elif (direction == Direction.UP and vwap_dev < 0) or \
             (direction == Direction.DOWN and vwap_dev > 0):
            predicted_prob = 0.5 + (predicted_prob - 0.5) * 1.05

        # --- VOLATILITY DAMPENING ---
        vol = volatility(prices)
        if vol > 0.0005:
            vol_factor = min(1.0, 0.0005 / vol)
            predicted_prob = 0.5 + (predicted_prob - 0.5) * max(0.3, vol_factor)

        # Clamp
        predicted_prob = max(0.50, min(0.95, predicted_prob))

        # --- EDGE CHECK ---
        market_prob = market.up_price if direction == Direction.UP else market.down_price
        edge = predicted_prob - market_prob - self.fee_pct

        if edge < self.min_edge:
            logger.debug(
                "Skip: edge=%.4f < %.4f (pred=%.3f mkt=%.3f mom=%.4f%% tfi=%.2f)",
                edge, self.min_edge, predicted_prob, market_prob, mom, tfi,
            )
            return None

        # --- CONFIDENCE (from secondary signals) ---
        rsi_val = rsi(prices, period=6)
        rsi_confirms = (direction == Direction.UP and rsi_val > 58) or (
            direction == Direction.DOWN and rsi_val < 42
        )
        accel = price_acceleration(prices)
        move_accelerating = (direction == Direction.UP and accel > 0) or (
            direction == Direction.DOWN and accel < 0
        )

        confidence = min(0.95, 0.5 + abs(mom) / 0.5)
        confirmations = 0
        if tfi_aligned and abs(tfi) > 0.3:
            confirmations += 1
            confidence = min(0.95, confidence + 0.05)
        if rsi_confirms:
            confirmations += 1
            confidence = min(0.95, confidence + 0.03)
        if move_accelerating:
            confirmations += 1
            confidence = min(0.95, confidence + 0.03)
        if consistency == 1.0:
            confirmations += 1

        # --- REASONING ---
        tfi_label = "buying" if tfi > 0 else "selling"
        tfi_strength = "strong" if abs(tfi) > 0.3 else "mild"
        vwap_label = f"{'above' if vwap_dev > 0 else 'below'} VWAP by {abs(vwap_dev):.3f}%"

        reasoning = (
            f"Pred {predicted_prob:.0%} {direction.value} vs market {market_prob:.0%} "
            f"→ {edge:.1%} edge. "
            f"BTC {mom:+.3f}% in {self.lookback_seconds}s, "
            f"TFI {tfi:+.2f} ({tfi_strength} {tfi_label}), "
            f"{vwap_label}, "
            f"consistency {consistency:.0%}, "
            f"RSI {rsi_val:.0f}. "
            f"{confirmations}/4 confirmations."
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
            "Signal: %s | mom=%.4f%% | tfi=%.2f | vwap=%.3f%% | pred=%.3f | mkt=%.3f | edge=%.3f | conf=%.2f",
            direction.value, mom, tfi, vwap_dev, predicted_prob, market_prob, edge, confidence,
        )

        return signal
