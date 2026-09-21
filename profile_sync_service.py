"""Passwordless watchlist profile sync.

Stores only a hashed sync ID and a normalized watchlist. There are no accounts,
emails or passwords. Anyone who knows the sync ID can read or overwrite the
associated list, so this endpoint is intentionally limited to non-sensitive
watchlist data.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/profile-sync", tags=["profile-sync"])

MAX_WATCHLIST = 20
SYNC_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,32}$")
SYMBOL_RE = re.compile(r"^[A-Z0-9.^=_-]{1,32}$")


class SyncPayload(BaseModel):
    watchlist: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_WATCHLIST)


def _normalize_sync_id(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not SYNC_ID_RE.fullmatch(normalized):
        raise ValueError("동기화 ID는 6~32자의 영문, 숫자, -, _만 사용할 수 있습니다.")
    return normalized


def _sync_key(sync_id: str) -> str:
    return hashlib.sha256(_normalize_sync_id(sync_id).encode("utf-8")).hexdigest()


def _normalize_watchlist(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if len(normalized) >= MAX_WATCHLIST:
            break
        symbol = str((row or {}).get("symbol") or (row or {}).get("ticker") or "").strip().upper()
        if not SYMBOL_RE.fullmatch(symbol) or symbol in seen:
            continue
        name = str((row or {}).get("name") or symbol).strip()[:80] or symbol
        normalized.append({"symbol": symbol, "name": name})
        seen.add(symbol)
    return normalized


def _database_url() -> str:
    return (
        os.environ.get("PROFILE_SYNC_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()


def _connect():
    database_url = _database_url()
    if not database_url:
        raise HTTPException(status_code=503, detail="관심종목 동기화 저장소가 아직 연결되지 않았습니다.")
    try:
        return psycopg.connect(database_url, connect_timeout=5)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="관심종목 동기화 저장소에 연결할 수 없습니다.") from exc


def _ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chartview_profile_sync (
            sync_key TEXT PRIMARY KEY,
            watchlist JSONB NOT NULL DEFAULT '[]'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


@router.get("/status")
def profile_sync_status():
    return {"configured": bool(_database_url())}


@router.get("/{sync_id}")
def load_profile(sync_id: str):
    try:
        normalized_id = _normalize_sync_id(sync_id)
        key = _sync_key(normalized_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with _connect() as conn:
        _ensure_table(conn)
        row = conn.execute(
            "SELECT watchlist, updated_at FROM chartview_profile_sync WHERE sync_key = %s",
            (key,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="저장된 동기화 ID가 없습니다.")

    watchlist, updated_at = row
    return {
        "syncId": normalized_id,
        "watchlist": _normalize_watchlist(watchlist or []),
        "updatedAt": updated_at.isoformat() if updated_at else None,
    }


@router.put("/{sync_id}")
def save_profile(sync_id: str, payload: SyncPayload):
    try:
        normalized_id = _normalize_sync_id(sync_id)
        key = _sync_key(normalized_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    watchlist = _normalize_watchlist(payload.watchlist)
    encoded = json.dumps(watchlist, ensure_ascii=False)

    with _connect() as conn:
        _ensure_table(conn)
        row = conn.execute(
            """
            INSERT INTO chartview_profile_sync (sync_key, watchlist, updated_at)
            VALUES (%s, %s::jsonb, NOW())
            ON CONFLICT (sync_key)
            DO UPDATE SET watchlist = EXCLUDED.watchlist, updated_at = NOW()
            RETURNING updated_at
            """,
            (key, encoded),
        ).fetchone()

    return {
        "ok": True,
        "syncId": normalized_id,
        "watchlist": watchlist,
        "updatedAt": row[0].isoformat() if row and row[0] else None,
    }
