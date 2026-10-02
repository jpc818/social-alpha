"""SQLite persistence for social mentions, prices, and paper trades."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS mentions (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    created_at TEXT,
                    ingested_at TEXT NOT NULL,
                    title TEXT,
                    body TEXT,
                    score INTEGER,
                    num_comments INTEGER,
                    url TEXT,
                    subreddit TEXT,
                    sentiment TEXT,
                    sentiment_score REAL,
                    tickers_json TEXT,
                    raw_json TEXT
                );

                CREATE TABLE IF NOT EXISTS prices (
                    ticker TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume REAL,
                    source TEXT,
                    PRIMARY KEY (ticker, ts)
                );

                CREATE TABLE IF NOT EXISTS paper_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty REAL NOT NULL,
                    price REAL NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    day_trade INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS paper_positions (
                    ticker TEXT PRIMARY KEY,
                    qty REAL NOT NULL,
                    avg_price REAL NOT NULL,
                    opened_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS paper_account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    cash REAL NOT NULL,
                    equity REAL NOT NULL,
                    starting_cash REAL NOT NULL,
                    day_trades_json TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def upsert_mention(self, mention: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO mentions (
                    id, source, created_at, ingested_at, title, body, score,
                    num_comments, url, subreddit, sentiment, sentiment_score,
                    tickers_json, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mention["id"],
                    mention.get("source", "reddit"),
                    mention.get("created_at"),
                    mention.get("ingested_at", utc_now()),
                    mention.get("title"),
                    mention.get("body"),
                    mention.get("score"),
                    mention.get("num_comments"),
                    mention.get("url"),
                    mention.get("subreddit"),
                    mention.get("sentiment"),
                    mention.get("sentiment_score"),
                    json.dumps(mention.get("tickers", [])),
                    json.dumps(mention.get("raw", mention), ensure_ascii=False),
                ),
            )

    def insert_price(self, ticker: str, price: float, ts: str | None = None, volume: float | None = None, source: str = "yfinance") -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO prices (ticker, ts, price, volume, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ticker.upper(), ts or utc_now(), float(price), volume, source),
            )

    def latest_prices(self) -> dict[str, float]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT p.ticker, p.price FROM prices p
                INNER JOIN (
                    SELECT ticker, MAX(ts) AS max_ts FROM prices GROUP BY ticker
                ) t ON p.ticker = t.ticker AND p.ts = t.max_ts
                """
            ).fetchall()
        return {row["ticker"]: row["price"] for row in rows}

    def recent_mentions(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mentions ORDER BY ingested_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["tickers"] = json.loads(item.pop("tickers_json") or "[]")
            out.append(item)
        return out

    def ensure_paper_account(self, starting_cash: float) -> None:
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM paper_account WHERE id = 1").fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO paper_account (id, cash, equity, starting_cash, day_trades_json, updated_at)
                    VALUES (1, ?, ?, ?, '[]', ?)
                    """,
                    (starting_cash, starting_cash, starting_cash, utc_now()),
                )

    def get_paper_account(self) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM paper_account WHERE id = 1").fetchone()
        if row is None:
            raise RuntimeError("Paper account not initialized")
        data = dict(row)
        data["day_trades"] = json.loads(data.pop("day_trades_json") or "[]")
        return data

    def save_paper_account(self, cash: float, equity: float, day_trades: list[str]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE paper_account
                SET cash = ?, equity = ?, day_trades_json = ?, updated_at = ?
                WHERE id = 1
                """,
                (cash, equity, json.dumps(day_trades), utc_now()),
            )

    def get_positions(self) -> dict[str, dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM paper_positions").fetchall()
        return {row["ticker"]: dict(row) for row in rows}

    def upsert_position(self, ticker: str, qty: float, avg_price: float, opened_at: str | None = None) -> None:
        ticker = ticker.upper()
        with self.connect() as conn:
            if qty <= 1e-9:
                conn.execute("DELETE FROM paper_positions WHERE ticker = ?", (ticker,))
                return
            existing = conn.execute(
                "SELECT opened_at FROM paper_positions WHERE ticker = ?", (ticker,)
            ).fetchone()
            opened = existing["opened_at"] if existing else (opened_at or utc_now())
            conn.execute(
                """
                INSERT OR REPLACE INTO paper_positions (ticker, qty, avg_price, opened_at)
                VALUES (?, ?, ?, ?)
                """,
                (ticker, qty, avg_price, opened),
            )

    def record_order(
        self,
        ticker: str,
        side: str,
        qty: float,
        price: float,
        status: str,
        reason: str = "",
        day_trade: bool = False,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO paper_orders (ts, ticker, side, qty, price, status, reason, day_trade)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (utc_now(), ticker.upper(), side, qty, price, status, reason, int(day_trade)),
            )

    def recent_orders(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM paper_orders ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
