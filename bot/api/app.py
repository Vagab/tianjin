"""FastAPI application factory."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from bot.api.routes import router as api_router
from bot.api.ws import ws_endpoint

if TYPE_CHECKING:
    from bot.db import Database
    from bot.main import TradingBot

logger = logging.getLogger(__name__)

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def create_app(bot: TradingBot, db: Database) -> FastAPI:
    app = FastAPI(title="Tianjin Dashboard API", docs_url="/api/docs")

    app.state.bot = bot
    app.state.db = db

    # CORS for dev (Vite runs on :5173)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(api_router, prefix="/api/v1")

    # Telegram webhook
    @app.post("/webhook/telegram")
    async def telegram_webhook(request: Request):
        data = await request.json()
        await bot.telegram.process_update(data)
        return {"ok": True}

    # WebSocket
    app.add_api_websocket_route("/ws", ws_endpoint)

    # Serve frontend static files if built
    if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
        # Mount assets separately so they get proper caching headers
        assets_dir = FRONTEND_DIST / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        # SPA catch-all: serve index.html for any non-API route
        @app.get("/{path:path}")
        async def serve_spa(path: str):
            # Try to serve the exact file first
            file_path = FRONTEND_DIST / path
            if path and file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            # Fall back to index.html for SPA routing
            return FileResponse(FRONTEND_DIST / "index.html")
    else:
        @app.get("/")
        async def no_frontend():
            return HTMLResponse(
                "<h1>Tianjin Dashboard</h1>"
                "<p>Frontend not built. Run <code>cd frontend && npm run build</code></p>"
                "<p><a href='/api/docs'>API Docs</a></p>"
            )

    return app
