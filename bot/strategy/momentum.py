"""V1 Momentum Strategy.

Maps recent BTC price momentum to a directional probability estimate.
Uses a logistic function to convert momentum magnitude into a probability,
then compares against Polymarket odds to find edge.
"""

from __future__ import annotations

import logging
import math
import time

from bot.market.models import Direction, Market
from bot.price.feed import BtcPriceFeed
from bot.price.indicators import momentum, rsi, volatility
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

        if len(prices) < 10:
            return None

        mom = momentum(prices)

        # Skip if move is too small
        if abs(mom) < self.min_move_pct:
            return None

        # Determine direction
        direction = Direction.UP if mom > 0 else Direction.DOWN

        # Convert momentum to probability via logistic function
        # Steepness calibrated so 0.1% move → ~60% probability, 0.3% → ~75%
        k = 15.0  # logistic steepness
        predicted_prob = 1 / (1 + math.exp(-k * mom / 100))

        # Adjust for volatility regime — high vol reduces confidence
        vol = volatility(prices)
        if vol > 0:
            # Dampen prediction when volatility is high
            vol_factor = min(1.0, 0.001 / vol)  # lower factor = more volatile
            predicted_prob = 0.5 + (predicted_prob - 0.5) * vol_factor

        # Get current market price for our direction
        market_prob = market.up_price if direction == Direction.UP else market.down_price

        # Edge = our predicted probability - market price - fees
        edge = predicted_prob - market_prob - self.fee_pct

        if edge < self.min_edge:
            return None

        # Confidence from RSI confirmation
        rsi_val = rsi(prices)
        rsi_confirms = (
            (direction == Direction.UP and rsi_val > 55)
            or (direction == Direction.DOWN and rsi_val < 45)
        )
        confidence = min(0.95, 0.5 + abs(mom) / 0.5)
        if rsi_confirms:
            confidence = min(0.95, confidence + 0.1)

        signal = Signal(
            direction=direction,
            confidence=confidence,
            predicted_prob=predicted_prob,
            market_prob=market_prob,
            edge=edge,
            timestamp=time.time(),
        )

        logger.info(
            "Signal: %s | mom=%.4f%% | pred=%.3f | mkt=%.3f | edge=%.3f | conf=%.2f",
            direction.value,
            mom,
            predicted_prob,
            market_prob,
            edge,
            confidence,
        )

        return signal
