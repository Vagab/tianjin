"""WebSocket connection manager for real-time updates."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from starlette.websockets import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._last_price_broadcast: float = 0.0

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
        logger.info("WebSocket client connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket):
        self._connections.remove(ws)
        logger.info("WebSocket client disconnected (%d total)", len(self._connections))

    async def broadcast(self, data: dict):
        """Send a message to all connected clients."""
        if not self._connections:
            return
        text = json.dumps(data)
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self._connections.remove(ws)
            except ValueError:
                pass

    async def broadcast_price(self, price: float, timestamp: float, volume: float = 0.0):
        """Broadcast price tick, throttled to 1/second."""
        now = time.time()
        if now - self._last_price_broadcast < 1.0:
            return
        self._last_price_broadcast = now
        await self.broadcast({
            "type": "price_tick",
            "price": price,
            "timestamp": timestamp,
            "volume": volume,
        })

    async def broadcast_trade(self, trade: dict):
        await self.broadcast({"type": "trade", **trade})

    async def broadcast_settlement(self, market_slug: str, outcome: str, pnl: float):
        await self.broadcast({
            "type": "settlement",
            "market_slug": market_slug,
            "outcome": outcome,
            "pnl": pnl,
        })

    async def broadcast_portfolio(self, portfolio: dict):
        await self.broadcast({"type": "portfolio_update", **portfolio})

    async def broadcast_status(self, status: dict):
        await self.broadcast({"type": "status_change", **status})


ws_manager = ConnectionManager()


async def ws_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, client can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
