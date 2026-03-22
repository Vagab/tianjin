"""SQLite database layer for persistent storage."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    market_slug TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('UP', 'DOWN')),
    amount_usd REAL NOT NULL,
    entry_price REAL NOT NULL,
    edge REAL NOT NULL DEFAULT 0,
    outcome TEXT CHECK (outcome IN ('win', 'loss') OR outcome IS NULL),
    pnl REAL NOT NULL DEFAULT 0,
    order_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trades_market ON trades(market_slug);

CREATE TABLE IF NOT EXISTS bot_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    initial_balance REAL NOT NULL,
    daily_start_balance REAL NOT NULL,
    daily_date TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS traded_markets (
    slug TEXT PRIMARY KEY,
    traded_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS price_ticks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    price REAL NOT NULL,
    volume REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_price_ticks_ts ON price_ticks(timestamp DESC);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    balance_usd REAL NOT NULL,
    daily_pnl REAL NOT NULL,
    total_pnl REAL NOT NULL,
    open_exposure REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity_snapshots(timestamp DESC);
"""


class Database:
    def __init__(self, db_path: str = "data/tianjin.db"):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        """Initialize database connection and create tables."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        logger.info("Database initialized: %s", self.db_path)

    async def close(self):
        if self._db:
            await self._db.close()

    # --- Trades ---

    async def insert_trade(
        self,
        timestamp: float,
        market_slug: str,
        direction: str,
        amount_usd: float,
        entry_price: float,
        edge: float = 0.0,
        outcome: str | None = None,
        pnl: float = 0.0,
        order_id: str | None = None,
    ) -> int:
        cursor = await self._db.execute(
            """INSERT INTO trades (timestamp, market_slug, direction, amount_usd,
               entry_price, edge, outcome, pnl, order_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, market_slug, direction, amount_usd, entry_price,
             edge, outcome, pnl, order_id),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def update_trade_outcome(
        self, market_slug: str, outcome: str, pnl: float,
    ):
        """Update the first pending trade for a market with its outcome."""
        await self._db.execute(
            """UPDATE trades SET outcome = ?, pnl = ?
               WHERE market_slug = ? AND outcome IS NULL
               LIMIT 1""",
            (outcome, pnl, market_slug),
        )
        await self._db.commit()

    async def get_trades(
        self,
        limit: int = 50,
        offset: int = 0,
        outcome: str | None = None,
    ) -> list[dict]:
        if outcome:
            rows = await self._db.execute_fetchall(
                """SELECT * FROM trades WHERE outcome = ?
                   ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
                (outcome, limit, offset),
            )
        else:
            rows = await self._db.execute_fetchall(
                "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [dict(r) for r in rows]

    async def get_all_trades(self) -> list[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM trades ORDER BY timestamp ASC",
        )
        return [dict(r) for r in rows]

    async def get_trade_stats(self) -> dict:
        row = await self._db.execute_fetchall(
            """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(pnl) as total_pnl,
                AVG(CASE WHEN outcome IS NOT NULL THEN edge END) as avg_edge,
                AVG(CASE WHEN outcome IS NOT NULL THEN pnl END) as avg_pnl
            FROM trades""",
        )
        r = dict(row[0]) if row else {}
        total = r.get("total", 0) or 0
        wins = r.get("wins", 0) or 0
        return {
            "total": total,
            "wins": wins,
            "losses": r.get("losses", 0) or 0,
            "win_rate": wins / total if total > 0 else 0.0,
            "total_pnl": r.get("total_pnl", 0.0) or 0.0,
            "avg_edge": r.get("avg_edge", 0.0) or 0.0,
            "avg_pnl": r.get("avg_pnl", 0.0) or 0.0,
        }

    async def count_trades(self, outcome: str | None = None) -> int:
        if outcome:
            rows = await self._db.execute_fetchall(
                "SELECT COUNT(*) as cnt FROM trades WHERE outcome = ?", (outcome,),
            )
        else:
            rows = await self._db.execute_fetchall("SELECT COUNT(*) as cnt FROM trades")
        return rows[0]["cnt"] if rows else 0

    # --- Bot State ---

    async def upsert_bot_state(
        self, initial_balance: float, daily_start_balance: float, daily_date: str,
    ):
        await self._db.execute(
            """INSERT INTO bot_state (id, initial_balance, daily_start_balance, daily_date)
               VALUES (1, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 initial_balance = excluded.initial_balance,
                 daily_start_balance = excluded.daily_start_balance,
                 daily_date = excluded.daily_date,
                 updated_at = datetime('now')""",
            (initial_balance, daily_start_balance, daily_date),
        )
        await self._db.commit()

    async def load_bot_state(self) -> dict | None:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM bot_state WHERE id = 1",
        )
        return dict(rows[0]) if rows else None

    # --- Traded Markets ---

    async def mark_traded(self, slug: str):
        await self._db.execute(
            """INSERT OR REPLACE INTO traded_markets (slug, traded_at) VALUES (?, ?)""",
            (slug, time.time()),
        )
        # Keep only last 50 entries
        await self._db.execute(
            """DELETE FROM traded_markets WHERE slug NOT IN (
                SELECT slug FROM traded_markets ORDER BY traded_at DESC LIMIT 50
            )""",
        )
        await self._db.commit()

    async def is_traded(self, slug: str) -> bool:
        rows = await self._db.execute_fetchall(
            "SELECT 1 FROM traded_markets WHERE slug = ?", (slug,),
        )
        return len(rows) > 0

    async def get_traded_slugs(self) -> set[str]:
        rows = await self._db.execute_fetchall("SELECT slug FROM traded_markets")
        return {r["slug"] for r in rows}

    # --- Price Ticks ---

    async def insert_price_tick(self, timestamp: float, price: float, volume: float = 0.0):
        await self._db.execute(
            "INSERT INTO price_ticks (timestamp, price, volume) VALUES (?, ?, ?)",
            (timestamp, price, volume),
        )
        await self._db.commit()

    async def get_price_ticks(self, since: float) -> list[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT timestamp, price, volume FROM price_ticks WHERE timestamp >= ? ORDER BY timestamp ASC",
            (since,),
        )
        return [dict(r) for r in rows]

    async def cleanup_price_ticks(self, max_age_seconds: float = 7 * 86400):
        cutoff = time.time() - max_age_seconds
        await self._db.execute("DELETE FROM price_ticks WHERE timestamp < ?", (cutoff,))
        await self._db.commit()

    # --- Equity Snapshots ---

    async def insert_equity_snapshot(
        self, timestamp: float, balance_usd: float, daily_pnl: float,
        total_pnl: float, open_exposure: float = 0.0,
    ):
        await self._db.execute(
            """INSERT INTO equity_snapshots (timestamp, balance_usd, daily_pnl, total_pnl, open_exposure)
               VALUES (?, ?, ?, ?, ?)""",
            (timestamp, balance_usd, daily_pnl, total_pnl, open_exposure),
        )
        await self._db.commit()

    async def get_equity_snapshots(self, since: float) -> list[dict]:
        rows = await self._db.execute_fetchall(
            """SELECT timestamp, balance_usd, daily_pnl, total_pnl, open_exposure
               FROM equity_snapshots WHERE timestamp >= ? ORDER BY timestamp ASC""",
            (since,),
        )
        return [dict(r) for r in rows]

    async def cleanup_equity_snapshots(self, max_age_seconds: float = 30 * 86400):
        cutoff = time.time() - max_age_seconds
        await self._db.execute("DELETE FROM equity_snapshots WHERE timestamp < ?", (cutoff,))
        await self._db.commit()

    # --- Migration from JSON ---

    async def migrate_from_json(self, base_dir: Path | None = None):
        """One-time migration from JSON/JSONL files into SQLite."""
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent

        # Check if trades already exist (skip if already migrated)
        count = await self.count_trades()
        if count > 0:
            logger.info("Database already has %d trades, skipping migration", count)
            return

        # Migrate trades.jsonl
        trades_file = base_dir / "trades.jsonl"
        if trades_file.exists():
            migrated = 0
            for line in trades_file.read_text().strip().splitlines():
                try:
                    t = json.loads(line)
                    await self._db.execute(
                        """INSERT INTO trades (timestamp, market_slug, direction,
                           amount_usd, entry_price, edge, outcome, pnl)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (t["timestamp"], t["market"], t["direction"],
                         t["amount"], t["entry_price"], t.get("edge", 0),
                         t.get("outcome"), t.get("pnl", 0)),
                    )
                    migrated += 1
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Skipping malformed trade line: %s", e)
            await self._db.commit()
            logger.info("Migrated %d trades from trades.jsonl", migrated)

        # Migrate bot_state.json
        state_file = base_dir / "bot_state.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
                await self.upsert_bot_state(
                    data["initial_balance"],
                    data["daily_start_balance"],
                    data.get("daily_date", ""),
                )
                logger.info("Migrated bot_state.json")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to migrate bot_state.json: %s", e)

        # Migrate traded_markets.json
        traded_file = base_dir / "traded_markets.json"
        if traded_file.exists():
            try:
                data = json.loads(traded_file.read_text())
                for slug in data.get("markets", []):
                    await self._db.execute(
                        "INSERT OR IGNORE INTO traded_markets (slug, traded_at) VALUES (?, ?)",
                        (slug, time.time()),
                    )
                await self._db.commit()
                logger.info("Migrated %d traded markets", len(data.get("markets", [])))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to migrate traded_markets.json: %s", e)
