"""V5 Momentum + Order Flow Strategy.

Signal flow:
1. Window-anchored momentum (BTC vs window open price)
2. Time-adaptive minimum move gate (stricter early, relaxed late)
3. Volatility-adaptive logistic k → base predicted_prob
4. TFI boost (aligned flow → up to +20%)
5. Acceleration boost/kill (+8% boost or kill on strong decel)
6. Edge check: predicted_prob - market_prob - fees >= 0.03
"""

from __future__ import annotations

import logging
import math
import time

from bot.market.models import Direction, Market
from bot.price.feed import BtcPriceFeed
from bot.price.indicators import (
    ema,
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

    async def evaluate(self, market: Market, price_feed: BtcPriceFeed, window_open_price: float | None = None) -> Signal | None:
        prices = price_feed.prices_since(self.lookback_seconds)
        ticks = price_feed.ticks_since(self.lookback_seconds)

        if len(prices) < 15:
            return None

        # --- PRIMARY SIGNAL: window-anchored momentum ---
        current_price = price_feed.current_price
        rolling_mom = momentum(prices)

        if window_open_price and window_open_price > 0:
            window_mom = (current_price - window_open_price) / window_open_price * 100
        else:
            window_mom = rolling_mom

        # --- WINDOW TIME WEIGHTING ---
        now_ts = ticks[-1].timestamp if ticks else time.time()
        elapsed = now_ts - market.start_ts
        window_duration = max(1, market.end_ts - market.start_ts)
        time_weight = min(1.0, max(0.0, elapsed / window_duration))

        # --- HARD GATE: time-adaptive minimum move ---
        adaptive_min = self.min_move_pct * (1.85 - time_weight)
        if abs(window_mom) < adaptive_min:
            return None

        direction = Direction.UP if window_mom > 0 else Direction.DOWN

        # --- BASE PROBABILITY (volatility-adaptive k) ---
        vol = volatility(prices)
        base_k = 200.0
        if vol > 0:
            k = base_k * min(2.0, max(0.5, 0.0003 / vol))
        else:
            k = base_k
        predicted_prob = 1 / (1 + math.exp(-k * abs(window_mom) / 100))

        # --- ROLLING MOMENTUM CONFIRMATION ---
        rolling_threshold = 0.05
        rolling_opposes = (direction == Direction.UP and rolling_mom < -rolling_threshold) or \
                          (direction == Direction.DOWN and rolling_mom > rolling_threshold)

        # --- CONSISTENCY (for confidence only, no dampening) ---
        consistency = momentum_consistency(prices, segments=3)

        # --- TFI: Trade Flow Imbalance ---
        tfi = trade_flow_imbalance(ticks)
        tfi_aligned = (direction == Direction.UP and tfi > 0) or (
            direction == Direction.DOWN and tfi < 0
        )
        tfi_opposing = (direction == Direction.UP and tfi < -0.2) or (
            direction == Direction.DOWN and tfi > 0.2
        )

        if tfi_aligned:
            tfi_boost = min(0.20, abs(tfi) * 0.25)
            predicted_prob += tfi_boost

        # --- ACCELERATION BOOST ---
        accel = price_acceleration(prices)
        accel_aligned = (direction == Direction.UP and accel > 0) or \
                        (direction == Direction.DOWN and accel < 0)
        accel_opposing = (direction == Direction.UP and accel < -0.02) or \
                         (direction == Direction.DOWN and accel > 0.02)
        if accel_aligned:
            predicted_prob += min(0.08, abs(accel) * 0.04)
        elif accel_opposing and abs(accel) > 0.02:
            return None

        # --- VWAP DEVIATION (for reasoning only) ---
        vwap_dev = vwap_deviation(ticks)

        # Clamp
        predicted_prob = max(0.50, min(0.97, predicted_prob))

        # --- EDGE CHECK ---
        market_prob = market.up_price if direction == Direction.UP else market.down_price
        edge = predicted_prob - market_prob - self.fee_pct

        if edge < self.min_edge:
            logger.debug(
                "Skip: edge=%.4f < %.4f (pred=%.3f mkt=%.3f mom=%.4f%% tfi=%.2f)",
                edge, self.min_edge, predicted_prob, market_prob, window_mom, tfi,
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

        confidence = min(0.95, 0.5 + abs(window_mom) / 0.5)
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

        rolling_label = f"recent {rolling_mom:+.3f}%/{self.lookback_seconds}s"
        if rolling_opposes:
            rolling_label += " (opposing)"

        reasoning = (
            f"Pred {predicted_prob:.0%} {direction.value} vs market {market_prob:.0%} "
            f"→ {edge:.1%} edge. "
            f"Window {window_mom:+.3f}% from open, {rolling_label}, "
            f"TFI {tfi:+.2f} ({tfi_strength} {tfi_label}), "
            f"{vwap_label}, "
            f"time {time_weight:.0%} elapsed. "
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
            "Signal: %s | w_mom=%.4f%% | r_mom=%.4f%% | tfi=%.2f | time=%.0f%% | pred=%.3f | mkt=%.3f | edge=%.3f",
            direction.value, window_mom, rolling_mom, tfi, time_weight * 100, predicted_prob, market_prob, edge,
        )

        return signal
