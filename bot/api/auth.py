"""Authentication middleware and helpers."""

from __future__ import annotations

import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Paths that don't require auth
PUBLIC_PATHS = {
    "/api/v1/auth/signup",
    "/api/v1/auth/login",
    "/api/v1/status",
    "/webhook/telegram",
    "/api/docs",
    "/api/openapi.json",
    "/ws",
}

# Paths that are always public (static files, SPA)
PUBLIC_PREFIXES = ("/assets/", "/favicon", "/icons")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for public paths
        if path in PUBLIC_PATHS or path == "/":
            return await call_next(request)

        # Skip auth for static assets
        for prefix in PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Skip auth for non-API paths (SPA catch-all)
        if not path.startswith("/api/"):
            return await call_next(request)

        # Check for session token
        token = request.cookies.get("session")
        if not token:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

        if not token:
            return Response(
                content='{"error":"unauthorized"}',
                status_code=401,
                media_type="application/json",
            )

        db = request.app.state.db
        account = await db.validate_session(token)
        if not account:
            return Response(
                content='{"error":"invalid or expired session"}',
                status_code=401,
                media_type="application/json",
            )

        # Attach account to request state
        request.state.account = account
        return await call_next(request)
