"""Real-time BTC price feed from Binance WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque

import websockets

from bot.market.models import PriceTick  # canonical location; re-exported here for compat

logger = logging.getLogger(__name__)


class BtcPriceFeed:
    def __init__(
        self,
        ws_url: str = "wss://stream.binance.com:9443/ws/btcusdt@trade",
        buffer_seconds: int = 360,
    ):
        self.ws_url = ws_url
        self.buffer_seconds = buffer_seconds
        self._ticks: deque[PriceTick] = deque()
        self._current_price: float = 0.0
        self._running = False
        self._task: asyncio.Task | None = None
        self._callbacks: list = []

    @property
    def current_price(self) -> float:
        return self._current_price

    @property
    def ticks(self) -> list[PriceTick]:
        return list(self._ticks)

    def on_price(self, callback):
        self._callbacks.append(callback)

    def prices_since(self, seconds_ago: float) -> list[float]:
        cutoff = time.time() - seconds_ago
        return [t.price for t in self._ticks if t.timestamp >= cutoff]

    def ticks_since(self, seconds_ago: float) -> list[PriceTick]:
        cutoff = time.time() - seconds_ago
        return [t for t in self._ticks if t.timestamp >= cutoff]

    def price_at(self, target_time: float) -> float | None:
        """Get the price closest to an absolute timestamp."""
        closest = None
        for tick in self._ticks:
            if closest is None or abs(tick.timestamp - target_time) < abs(closest.timestamp - target_time):
                closest = tick
        if closest and abs(closest.timestamp - target_time) > 30:
            return None  # no tick within 30s of target — data too stale
        return closest.price if closest else None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self):
        while self._running:
            try:
                await self._connect()
            except Exception as e:
                logger.error("WebSocket error: %s. Reconnecting in 3s...", e)
                await asyncio.sleep(3)

    async def _connect(self):
        logger.info("Connecting to Binance WebSocket: %s", self.ws_url)
        async for ws in websockets.connect(self.ws_url):
            logger.info("Connected to Binance price feed")
            try:
                async for msg in ws:
                    if not self._running:
                        return
                    self._handle_message(msg)
            except websockets.ConnectionClosed:
                logger.warning("Binance WebSocket disconnected")
                if not self._running:
                    return
                continue

    def _handle_message(self, raw: str):
        data = json.loads(raw)
        tick = PriceTick(
            price=float(data["p"]),
            timestamp=float(data["T"]) / 1000.0,
            volume=float(data.get("q", 0)),
            is_buyer_maker=bool(data.get("m", False)),
        )
        self._current_price = tick.price
        self._ticks.append(tick)

        # Prune old ticks
        cutoff = time.time() - self.buffer_seconds
        while self._ticks and self._ticks[0].timestamp < cutoff:
            self._ticks.popleft()

        for cb in self._callbacks:
            try:
                cb(tick)
            except Exception as e:
                logger.error("Price callback error: %s", e)

    async def wait_for_price(self, timeout: float = 30.0) -> float:
        start = time.time()
        while self._current_price == 0.0:
            if time.time() - start > timeout:
                raise TimeoutError("No BTC price received within timeout")
            await asyncio.sleep(0.1)
        return self._current_price


if __name__ == "__main__":
    async def _demo():
        feed = BtcPriceFeed()
        await feed.start()
        price = await feed.wait_for_price()
        print(f"BTC price: ${price:,.2f}")
        await asyncio.sleep(5)
        prices = feed.prices_since(5)
        print(f"Got {len(prices)} ticks in 5s")
        if prices:
            print(f"Range: ${min(prices):,.2f} - ${max(prices):,.2f}")
        await feed.stop()

    asyncio.run(_demo())
