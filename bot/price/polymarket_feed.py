"""Polymarket WebSocket feeds: market data, fill confirmation, settlement.

PolymarketFeed — market channel for real-time price data (replaces BtcPriceFeed).
UserFeed — authenticated user channel for order fill/cancel events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass

import websockets

from bot.market.models import PriceTick

logger = logging.getLogger(__name__)

POLYMARKET_WS_BASE = "wss://ws-subscriptions-clob.polymarket.com/ws"
PING_INTERVAL = 10  # Polymarket requires PING every 10s


@dataclass
class FillResult:
    filled: bool
    fill_price: float = 0.0
    fill_size: float = 0.0
    order_id: str = ""
    status: str = ""  # MATCHED, MINED, CONFIRMED, FAILED


# ---------------------------------------------------------------------------
# PolymarketFeed — replaces BtcPriceFeed as primary price source
# ---------------------------------------------------------------------------


class PolymarketFeed:
    """Real-time Polymarket market channel feed.

    Subscribes to a market's token IDs, tracks last_trade_price events as
    PriceTick objects, maintains best bid/ask from price_change events,
    and listens for market_resolved events.

    Implements the same public API as BtcPriceFeed so MomentumStrategy
    works without changes.
    """

    def __init__(self, buffer_seconds: int = 360):
        self.buffer_seconds = buffer_seconds
        self._ticks: deque[PriceTick] = deque()
        self._current_price: float = 0.0
        self._best_bid: float = 0.0
        self._best_ask: float = 0.0
        self._last_tick_time: float = 0.0
        self._running = False
        self._task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None
        self._ws = None
        self._subscribed_assets: list[str] = []
        self._primary_asset_id: str = ""  # only track prices for this asset
        self._callbacks: list = []

        # Settlement
        self._resolution_event = asyncio.Event()
        self._winning_asset_id: str | None = None

        # Startup sync
        self._initial_data = asyncio.Event()

    # --- Public API (matches BtcPriceFeed) ---

    @property
    def current_price(self) -> float:
        return self._current_price

    @property
    def best_bid(self) -> float:
        return self._best_bid

    @property
    def best_ask(self) -> float:
        return self._best_ask

    @property
    def midpoint(self) -> float:
        if self._best_bid > 0 and self._best_ask > 0:
            return (self._best_bid + self._best_ask) / 2
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
        closest = None
        for tick in self._ticks:
            if closest is None or abs(tick.timestamp - target_time) < abs(closest.timestamp - target_time):
                closest = tick
        if closest and abs(closest.timestamp - target_time) > 30:
            return None
        return closest.price if closest else None

    def is_stale(self, threshold: float = 10.0) -> bool:
        if self._last_tick_time == 0:
            return True
        return time.time() - self._last_tick_time > threshold

    # --- Lifecycle ---

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._running = False
        if self._ping_task:
            self._ping_task.cancel()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def wait_for_initial_data(self, timeout: float = 30.0):
        """Block until first price data arrives."""
        await asyncio.wait_for(self._initial_data.wait(), timeout=timeout)

    # --- Subscription ---

    async def subscribe(self, asset_ids: list[str], primary_asset_id: str = ""):
        """Subscribe to a market's token IDs.

        Args:
            asset_ids: All token IDs to subscribe to (for resolution events).
            primary_asset_id: Only record price ticks for this asset.
                If empty, records ticks for all assets.
        """
        # Clear old data for new market
        self._ticks.clear()
        self._current_price = 0.0
        self._best_bid = 0.0
        self._best_ask = 0.0
        self._resolution_event.clear()
        self._winning_asset_id = None
        self._initial_data.clear()
        self._subscribed_assets = asset_ids
        self._primary_asset_id = primary_asset_id

        if self._ws:
            try:
                await self._ws.send(json.dumps({
                    "assets_ids": asset_ids,
                    "type": "market",
                    "initial_dump": True,
                    "custom_feature_enabled": True,
                }))
                logger.info("Subscribed to market with %d assets", len(asset_ids))
            except Exception as e:
                logger.error("Subscribe error: %s", e)

    async def unsubscribe(self):
        if self._ws and self._subscribed_assets:
            try:
                await self._ws.send(json.dumps({
                    "operation": "unsubscribe",
                    "assets_ids": self._subscribed_assets,
                }))
            except Exception:
                pass
        self._subscribed_assets = []

    # --- Settlement ---

    async def wait_for_resolution(self, timeout: float = 360.0) -> str | None:
        """Wait for market_resolved event. Returns winning_asset_id or None."""
        try:
            await asyncio.wait_for(self._resolution_event.wait(), timeout=timeout)
            return self._winning_asset_id
        except asyncio.TimeoutError:
            return None

    # --- Internal ---

    async def _run(self):
        backoff = 1
        while self._running:
            try:
                await self._connect()
                backoff = 1
            except Exception as e:
                logger.error("Market WS error: %s. Reconnecting in %ds...", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _connect(self):
        url = f"{POLYMARKET_WS_BASE}/market"
        logger.info("Connecting to Polymarket Market WebSocket...")

        async for ws in websockets.connect(url):
            self._ws = ws
            try:
                # Re-subscribe if we had assets
                if self._subscribed_assets:
                    await ws.send(json.dumps({
                        "assets_ids": self._subscribed_assets,
                        "type": "market",
                        "initial_dump": True,
                        "custom_feature_enabled": True,
                    }))

                self._ping_task = asyncio.create_task(self._ping_loop(ws))

                async for msg in ws:
                    if not self._running:
                        return
                    if msg == "PONG":
                        continue
                    self._handle_message(msg)

            except websockets.ConnectionClosed:
                logger.warning("Market WS disconnected")
                if self._ping_task:
                    self._ping_task.cancel()
                if not self._running:
                    return
                continue

    def _handle_message(self, raw: str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # initial_dump sends an array of events
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    self._process_event(item)
            return

        if isinstance(data, dict):
            self._process_event(data)

    def _process_event(self, data: dict):
        self._last_tick_time = time.time()
        event_type = data.get("event_type")

        if event_type == "last_trade_price":
            self._handle_trade(data)
        elif event_type == "price_change":
            self._handle_price_change(data)
        elif event_type == "market_resolved":
            self._handle_resolution(data)

    def _handle_trade(self, data: dict):
        """last_trade_price event → PriceTick."""
        # Filter by primary asset if set
        asset_id = data.get("asset_id", "")
        if self._primary_asset_id and asset_id and asset_id != self._primary_asset_id:
            return

        price = float(data.get("price", 0))
        size = float(data.get("size", 0))
        side = data.get("side", "")
        ts_ms = data.get("timestamp", "")

        if price <= 0:
            return

        ts = float(ts_ms) / 1000.0 if ts_ms else time.time()

        # side == "SELL" means seller was taker (aggressor) → is_buyer_maker=True
        is_buyer_maker = side == "SELL"

        tick = PriceTick(
            price=price,
            timestamp=ts,
            volume=size,
            is_buyer_maker=is_buyer_maker,
        )
        self._current_price = price
        self._ticks.append(tick)

        # Prune old ticks
        cutoff = time.time() - self.buffer_seconds
        while self._ticks and self._ticks[0].timestamp < cutoff:
            self._ticks.popleft()

        # Signal initial data ready
        if not self._initial_data.is_set():
            self._initial_data.set()

        for cb in self._callbacks:
            try:
                cb(tick)
            except Exception as e:
                logger.error("Price callback error: %s", e)

    def _handle_price_change(self, data: dict):
        """price_change event → update best bid/ask."""
        for change in data.get("price_changes", []):
            best_bid = change.get("best_bid")
            best_ask = change.get("best_ask")
            if best_bid:
                self._best_bid = float(best_bid)
            if best_ask:
                self._best_ask = float(best_ask)

            # Use midpoint as current price if no trades yet
            if self._current_price == 0 and self._best_bid > 0 and self._best_ask > 0:
                self._current_price = (self._best_bid + self._best_ask) / 2
                if not self._initial_data.is_set():
                    self._initial_data.set()

    def _handle_resolution(self, data: dict):
        winning = data.get("winning_asset_id", "")
        logger.info(
            "Market resolved: condition=%s winning=%s outcome=%s",
            data.get("market", "")[:16],
            winning[:16] if winning else "?",
            data.get("winning_outcome", ""),
        )
        self._winning_asset_id = winning
        self._resolution_event.set()

    async def _ping_loop(self, ws):
        try:
            while self._running:
                await asyncio.sleep(PING_INTERVAL)
                await ws.send("PING")
        except (asyncio.CancelledError, websockets.ConnectionClosed):
            pass


# ---------------------------------------------------------------------------
# UserFeed — authenticated WS for order fill/cancel events
# ---------------------------------------------------------------------------


class UserFeed:
    """Authenticated WebSocket for real-time order fill/cancel events.

    Usage:
        feed = UserFeed(api_key, secret, passphrase)
        await feed.start()
        result = await feed.wait_for_fill(order_id, timeout=30.0)
    """

    def __init__(self, api_key: str, secret: str, passphrase: str):
        self._api_key = api_key
        self._secret = secret
        self._passphrase = passphrase
        self._pending: dict[str, asyncio.Future] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None
        self._ws = None
        self._connected = asyncio.Event()

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._running = False
        if self._ping_task:
            self._ping_task.cancel()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        for future in self._pending.values():
            if not future.done():
                future.set_result(FillResult(filled=False, status="feed_stopped"))
        self._pending.clear()

    async def wait_for_fill(self, order_id: str, timeout: float = 30.0) -> FillResult:
        """Wait for an order to be filled or cancelled."""
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending[order_id] = future

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning("Fill timeout for order %s after %.0fs", order_id, timeout)
            return FillResult(filled=False, order_id=order_id, status="timeout")
        finally:
            self._pending.pop(order_id, None)

    async def _run(self):
        backoff = 1
        while self._running:
            try:
                await self._connect()
                backoff = 1
            except Exception as e:
                logger.error("User WS error: %s. Reconnecting in %ds...", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _connect(self):
        url = f"{POLYMARKET_WS_BASE}/user"
        logger.info("Connecting to Polymarket User WebSocket...")

        async for ws in websockets.connect(url):
            self._ws = ws
            try:
                await ws.send(json.dumps({
                    "auth": {
                        "apiKey": self._api_key,
                        "secret": self._secret,
                        "passphrase": self._passphrase,
                    },
                    "type": "user",
                }))
                logger.info("User WS authenticated")
                self._connected.set()

                self._ping_task = asyncio.create_task(self._ping_loop(ws))

                async for msg in ws:
                    if not self._running:
                        return
                    if msg == "PONG":
                        continue
                    self._handle_message(msg)

            except websockets.ConnectionClosed:
                logger.warning("User WS disconnected")
                self._connected.clear()
                if self._ping_task:
                    self._ping_task.cancel()
                if not self._running:
                    return
                continue

    def _handle_message(self, raw: str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    self._process_user_event(item)
            return

        if isinstance(data, dict):
            self._process_user_event(data)

    def _process_user_event(self, data: dict):
        event_type = data.get("event_type")
        if event_type == "trade":
            self._handle_trade(data)
        elif event_type == "order":
            self._handle_order(data)

    def _handle_trade(self, data: dict):
        taker_order_id = data.get("taker_order_id", "")
        status = data.get("status", "")
        price = float(data.get("price", 0))
        size = float(data.get("size", 0))

        logger.info(
            "Trade event: order=%s status=%s price=%.3f size=%.2f",
            taker_order_id[:16], status, price, size,
        )

        future = self._pending.get(taker_order_id)
        if future and not future.done():
            if status in ("MATCHED", "MINED", "CONFIRMED"):
                future.set_result(FillResult(
                    filled=True,
                    fill_price=price,
                    fill_size=size,
                    order_id=taker_order_id,
                    status=status,
                ))
            elif status == "FAILED":
                future.set_result(FillResult(
                    filled=False,
                    order_id=taker_order_id,
                    status="FAILED",
                ))

    def _handle_order(self, data: dict):
        order_id = data.get("id", "")
        order_type = data.get("type", "")
        status = data.get("status", "")

        if order_type == "CANCELLATION" or status == "CANCELED":
            logger.info("Order cancelled: %s", order_id[:16])
            future = self._pending.get(order_id)
            if future and not future.done():
                future.set_result(FillResult(
                    filled=False,
                    order_id=order_id,
                    status="CANCELED",
                ))

    async def _ping_loop(self, ws):
        try:
            while self._running:
                await asyncio.sleep(PING_INTERVAL)
                await ws.send("PING")
        except (asyncio.CancelledError, websockets.ConnectionClosed):
            pass
