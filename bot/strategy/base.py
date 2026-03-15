"""Abstract strategy interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from bot.market.models import Market
from bot.price.feed import BtcPriceFeed
from bot.strategy.signal import Signal


class Strategy(ABC):
    @abstractmethod
    async def evaluate(self, market: Market, price_feed: BtcPriceFeed, window_open_price: float | None = None) -> Signal | None:
        """Return a Signal if there's a trade, None otherwise."""
