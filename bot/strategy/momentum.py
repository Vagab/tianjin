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
        # The contract settles on: is BTC above or below the window open price?
        # This directly predicts the settlement outcome.
        current_price = price_feed.current_price
        rolling_mom = momentum(prices)  # 45s rolling (used as confirmation)

        if window_open_price and window_open_price > 0:
            window_mom = (current_price - window_open_price) / window_open_price * 100
        else:
            window_mom = rolling_mom  # fallback

        # --- HARD GATE: minimum move ---
        if abs(window_mom) < self.min_move_pct:
            return None

        direction = Direction.UP if window_mom > 0 else Direction.DOWN

        # --- BASE PROBABILITY (volatility-adaptive k) ---
        vol = volatility(prices)
        # In low-vol regimes, a small move is more meaningful → higher k
        # In high-vol regimes, a move could be noise → lower k
        # Base k=200 at vol=0.0003, scales inversely
        base_k = 200.0
        if vol > 0:
            k = base_k * min(2.0, max(0.5, 0.0003 / vol))
        else:
            k = base_k
        predicted_prob = 1 / (1 + math.exp(-k * abs(window_mom) / 100))

        # --- WINDOW TIME WEIGHTING ---
        # Use latest tick timestamp for backtest compatibility
        now_ts = ticks[-1].timestamp if ticks else time.time()
        elapsed = now_ts - market.start_ts
        window_duration = max(1, market.end_ts - market.start_ts)
        time_weight = min(1.0, max(0.0, elapsed / window_duration))

        # Early in window → dampen edge (move not yet established)
        # Late in window → full weight (move has persisted)
        predicted_prob = 0.5 + (predicted_prob - 0.5) * (0.5 + 0.5 * time_weight)

        # --- ROLLING MOMENTUM CONFIRMATION ---
        # If recent 45s trend opposes the window-level direction, dampen
        rolling_threshold = 0.05  # fixed threshold, decoupled from min_move_pct
        rolling_opposes = (direction == Direction.UP and rolling_mom < -rolling_threshold) or \
                          (direction == Direction.DOWN and rolling_mom > rolling_threshold)
        if rolling_opposes:
            predicted_prob = 0.5 + (predicted_prob - 0.5) * 0.6

        # --- EMA TREND FILTER ---
        # Fast EMA vs slow EMA — if they disagree with direction, dampen
        if len(prices) >= 15:
            fast_ema = ema(prices, period=5)
            slow_ema = ema(prices, period=15)
            ema_trend_up = fast_ema > slow_ema
            if (direction == Direction.UP and not ema_trend_up) or \
               (direction == Direction.DOWN and ema_trend_up):
                predicted_prob = 0.5 + (predicted_prob - 0.5) * 0.5

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

        # TFI opposing → dampen instead of kill (to allow more trades)
        if tfi_opposing:
            predicted_prob = 0.5 + (predicted_prob - 0.5) * 0.5
        elif tfi_aligned:
            tfi_boost = min(0.08, abs(tfi) * 0.1)  # max +8% boost
            predicted_prob += tfi_boost


        # --- ACCELERATION BOOST ---
        # If the move is accelerating (2nd half faster than 1st), it's more likely to persist
        accel = price_acceleration(prices)
        accel_aligned = (direction == Direction.UP and accel > 0) or \
                        (direction == Direction.DOWN and accel < 0)
        accel_opposing = (direction == Direction.UP and accel < -0.02) or \
                         (direction == Direction.DOWN and accel > 0.02)
        if accel_aligned:
            predicted_prob += min(0.04, abs(accel) * 0.02)
        elif accel_opposing and abs(accel) > 0.03:
            # Strong deceleration = move is fading, kill
            return None

        # --- VWAP DEVIATION (for reasoning only) ---
        vwap_dev = vwap_deviation(ticks)

        # Clamp
        predicted_prob = max(0.50, min(0.95, predicted_prob))

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
            rolling_label += " (opposing, dampened)"

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
