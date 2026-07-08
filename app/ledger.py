"""Durable settlement ledger + per-nonce idempotency.

Every paid call is recorded keyed on the EIP-3009 authorization nonce (the unit
of payment). The ledger gives (a) a revenue/audit trail tying an on-chain charge
to the tool + data delivered, and (b) an idempotency primitive: ``claim`` is an
atomic INSERT — only the first request for a given nonce proceeds; concurrent or
retried duplicates are rejected, preventing double-execution / double-delivery.

Storage is SQLite (stdlib, no new deps). Writes are serialized behind a lock and
run off the event loop via ``asyncio.to_thread``. For audit durability across
container restarts, mount a persistent volume at the ledger dir (see config);
every settlement is ALSO emitted as a structured log line as a durable backstop.
"""

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from typing import Optional

from .config import settings

logger = logging.getLogger("content_copilot_gateway.ledger")

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settlements (
    nonce         TEXT PRIMARY KEY,
    tool          TEXT NOT NULL,
    payer         TEXT,
    amount        TEXT,                 -- atomic USD₮0 units (6 decimals)
    served_at     REAL NOT NULL,
    settle_status TEXT NOT NULL DEFAULT 'served',  -- served | settled | failed | released
    tx_hash       TEXT,
    settled_at    REAL
);
CREATE INDEX IF NOT EXISTS idx_settlements_status ON settlements(settle_status);
"""


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = settings.ledger_path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(_SCHEMA)
        _conn.commit()
    return _conn


def _claim(nonce: str, tool: str, payer: Optional[str], amount: Optional[str]) -> bool:
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO settlements (nonce, tool, payer, amount, served_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (nonce, tool, payer, amount, time.time()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # nonce already claimed -> duplicate


def _release(nonce: str) -> None:
    with _lock:
        conn = _connect()
        # Only release a row that never settled (lets a legitimate retry through).
        conn.execute(
            "DELETE FROM settlements WHERE nonce = ? AND settle_status = 'served'",
            (nonce,),
        )
        conn.commit()


def _mark(nonce: str, status: str, tx_hash: Optional[str] = None) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE settlements SET settle_status = ?, tx_hash = COALESCE(?, tx_hash), "
            "settled_at = ? WHERE nonce = ?",
            (status, tx_hash, time.time(), nonce),
        )
        conn.commit()


def _explorer_url(tx_hash: Optional[str]) -> Optional[str]:
    return f"{settings.explorer_tx_base}{tx_hash}" if tx_hash else None


def _list(limit: int, offset: int, status: Optional[str]) -> dict:
    """Paginated, newest-first settlement rows for the revenue dashboard."""
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    with _lock:
        conn = _connect()
        where = "WHERE settle_status = ?" if status else ""
        args: tuple = (status,) if status else ()
        total = conn.execute(
            f"SELECT COUNT(*) FROM settlements {where}", args
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT nonce, tool, payer, amount, served_at, settle_status, tx_hash, settled_at "
            f"FROM settlements {where} ORDER BY served_at DESC LIMIT ? OFFSET ?",
            (*args, limit, offset),
        ).fetchall()
    txns = []
    for r in rows:
        amount_atomic = int(r[3]) if r[3] and str(r[3]).isdigit() else 0
        txns.append({
            "nonce": r[0],
            "tool": r[1],
            "payer": r[2],
            "amount_atomic": amount_atomic,
            "amount_usdt0": round(amount_atomic / 1e6, 6),
            "served_at": r[4],
            "status": r[5],
            "tx_hash": r[6],
            "explorer_url": _explorer_url(r[6]),
            "settled_at": r[7],
        })
    return {"transactions": txns, "total": total, "limit": limit, "offset": offset}


def _summary() -> dict:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT settle_status, COUNT(*), COALESCE(SUM(CAST(amount AS INTEGER)), 0) "
            "FROM settlements GROUP BY settle_status"
        ).fetchall()
    by_status = {r[0]: {"count": r[1], "amount_atomic": r[2]} for r in rows}
    settled = by_status.get("settled", {})
    served = by_status.get("served", {})
    # Revenue = settled (confirmed on-chain) + served (2xx delivered, settle pending/assumed).
    revenue_atomic = settled.get("amount_atomic", 0) + served.get("amount_atomic", 0)
    return {
        "by_status": by_status,
        "revenue_usdt0": round(revenue_atomic / 1e6, 6),
        "settled_count": settled.get("count", 0),
        "served_count": served.get("count", 0),
    }


# --- async wrappers (run sync sqlite off the event loop) ---------------------
async def claim(nonce: str, tool: str, payer: Optional[str], amount: Optional[str]) -> bool:
    """Atomically claim a nonce. Returns False if already claimed (duplicate)."""
    return await asyncio.to_thread(_claim, nonce, tool, payer, amount)


async def release(nonce: str) -> None:
    """Release an unsettled claim so a legitimate retry can proceed."""
    await asyncio.to_thread(_release, nonce)


async def mark_settled(nonce: str, tx_hash: Optional[str]) -> None:
    await asyncio.to_thread(_mark, nonce, "settled", tx_hash)
    logger.info(json.dumps({"event": "settlement", "nonce": nonce, "tx_hash": tx_hash}))


async def mark_failed(nonce: str) -> None:
    await asyncio.to_thread(_mark, nonce, "failed", None)


async def summary() -> dict:
    return await asyncio.to_thread(_summary)


async def transactions(limit: int = 100, offset: int = 0, status: Optional[str] = None) -> dict:
    """Paginated settlement rows (newest first) for the operator revenue dashboard."""
    return await asyncio.to_thread(_list, limit, offset, status)
