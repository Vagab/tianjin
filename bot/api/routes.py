"""REST API routes."""

from __future__ import annotations

import time

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel

from bot.api.models import (
    EquitySnapshotResponse,
    MarketResponse,
    PortfolioResponse,
    PriceTickResponse,
    RiskResponse,
    StatusResponse,
    TradeResponse,
    TradeStatsResponse,
    TradesListResponse,
)

router = APIRouter()


def _get_bot(request: Request):
    return request.app.state.bot


def _get_db(request: Request):
    return request.app.state.db


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# --- Auth ---

class LoginRequest(BaseModel):
    key: str


@router.post("/auth/signup")
async def signup(request: Request, response: Response):
    db = _get_db(request)
    ip = _get_ip(request)

    # Rate limit: max 5 signups per IP per hour
    failures = await db.count_recent_failures(ip, window_seconds=3600)
    if failures > 20:
        return Response(
            content='{"error":"too many attempts, try again later"}',
            status_code=429,
            media_type="application/json",
        )

    account_id, uid, key = await db.create_account()
    token = await db.create_session(account_id, ip)
    await db.record_auth_attempt(ip, success=True)

    response.set_cookie(
        "session", token,
        httponly=True, samesite="lax", secure=True, max_age=30 * 86400,
    )
    return {"uid": uid, "key": key, "token": token}


@router.post("/auth/login")
async def login(request: Request, body: LoginRequest, response: Response):
    db = _get_db(request)
    ip = _get_ip(request)

    # Rate limit: max 10 failed attempts per IP per 15 min
    failures = await db.count_recent_failures(ip, window_seconds=900)
    if failures >= 10:
        return Response(
            content='{"error":"too many failed attempts, try again in 15 minutes"}',
            status_code=429,
            media_type="application/json",
        )

    # Strip spaces/dashes from key
    key = body.key.replace(" ", "").replace("-", "")

    account = await db.authenticate(key)
    if not account:
        await db.record_auth_attempt(ip, success=False)
        return Response(
            content='{"error":"invalid key"}',
            status_code=401,
            media_type="application/json",
        )

    await db.record_auth_attempt(ip, success=True)
    token = await db.create_session(account["id"], ip)

    response.set_cookie(
        "session", token,
        httponly=True, samesite="lax", secure=True, max_age=30 * 86400,
    )
    return {"uid": account["uid"], "token": token}


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session")
    if token:
        db = _get_db(request)
        await db.delete_session(token)
    response.delete_cookie("session")
    return {"ok": True}


@router.get("/auth/me")
async def me(request: Request):
    account = request.state.account
    return {"uid": account["uid"]}


# --- Portfolio ---

@router.get("/portfolio", response_model=PortfolioResponse)
async def get_portfolio(request: Request):
    bot = _get_bot(request)
    portfolio = bot.executor.portfolio
    return PortfolioResponse(
        balance_usd=portfolio.balance_usd,
        daily_pnl=portfolio.daily_pnl,
        total_pnl=portfolio.total_pnl,
        open_exposure=portfolio.open_exposure,
        open_positions=len(portfolio.open_positions),
        win_rate=portfolio.win_rate,
    )


# --- Trades ---

@router.get("/trades", response_model=TradesListResponse)
async def get_trades(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    outcome: str | None = Query(None),
):
    db = _get_db(request)
    trades = await db.get_trades(limit=limit, offset=offset, outcome=outcome)
    total = await db.count_trades(outcome=outcome)
    return TradesListResponse(
        trades=[TradeResponse(**t) for t in trades],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/trades/stats", response_model=TradeStatsResponse)
async def get_trade_stats(request: Request):
    db = _get_db(request)
    stats = await db.get_trade_stats()
    return TradeStatsResponse(**stats)


@router.get("/trades/{uid}")
async def get_trade_by_uid(request: Request, uid: str):
    db = _get_db(request)
    trade = await db.get_trade_by_uid(uid)
    if not trade:
        return Response(content='{"error":"not found"}', status_code=404, media_type="application/json")
    return TradeResponse(**trade)


# --- Status ---

@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request):
    bot = _get_bot(request)
    current_market = None
    market_end_ts = None
    if hasattr(bot, "_current_market") and bot._current_market:
        current_market = bot._current_market.slug
        market_end_ts = float(bot._current_market.end_ts)
    return StatusResponse(
        running=bot._running,
        halted=bot.risk._halted,
        paper_trading=bot.executor.__class__.__name__ == "PaperExecutor",
        current_market=current_market,
        market_end_ts=market_end_ts,
        uptime_seconds=time.time() - bot._start_time if hasattr(bot, "_start_time") else 0,
    )


# --- Risk ---

@router.get("/risk", response_model=RiskResponse)
async def get_risk(request: Request):
    bot = _get_bot(request)
    risk = bot.risk
    return RiskResponse(
        max_position_usd=risk.max_position_usd,
        max_exposure_usd=risk.max_exposure_usd,
        max_daily_loss_usd=risk.max_daily_loss_usd,
        kelly_fraction=risk.kelly_fraction,
        min_edge=risk.min_edge,
        consecutive_losses=risk._consecutive_losses,
        halted=risk._halted,
    )


# --- Prices ---

@router.get("/prices", response_model=list[PriceTickResponse])
async def get_prices(
    request: Request,
    since: float = Query(default=0, description="Unix timestamp"),
):
    db = _get_db(request)
    if since <= 0:
        since = time.time() - 86400
    ticks = await db.get_price_ticks(since)
    return [PriceTickResponse(**t) for t in ticks]


# --- Equity ---

@router.get("/equity", response_model=list[EquitySnapshotResponse])
async def get_equity(
    request: Request,
    since: float = Query(default=0, description="Unix timestamp"),
):
    db = _get_db(request)
    if since <= 0:
        since = time.time() - 7 * 86400
    snapshots = await db.get_equity_snapshots(since)
    return [EquitySnapshotResponse(**s) for s in snapshots]


# --- Market ---

@router.get("/market")
async def get_market(request: Request):
    bot = _get_bot(request)
    if hasattr(bot, "_current_market") and bot._current_market:
        m = bot._current_market
        return MarketResponse(
            slug=m.slug,
            question=m.question,
            up_price=m.up_price,
            down_price=m.down_price,
            start_ts=m.start_ts,
            end_ts=m.end_ts,
            active=m.active,
        )
    return {"market": None}


# --- Controls ---

@router.post("/control/halt")
async def halt_trading(request: Request):
    bot = _get_bot(request)
    bot.risk.force_halt()
    return {"status": "halted"}


@router.post("/control/resume")
async def resume_trading(request: Request):
    bot = _get_bot(request)
    bot.risk.resume()
    return {"status": "resumed"}
