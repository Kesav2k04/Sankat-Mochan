"""PostgreSQL persistence for isolated command-post run sessions.

Every process start creates a new session. The live Store intentionally starts empty;
PostgreSQL retains snapshots and voice bytes for audit/history without repopulating the
new dashboard. asyncpg is Apache-2.0 licensed (project rule #1).
"""
from __future__ import annotations

import json
import os
import socket
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg


SCHEMA = """
CREATE TABLE IF NOT EXISTS command_post_sessions (
    id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    host TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS command_post_snapshots (
    session_id UUID PRIMARY KEY REFERENCES command_post_sessions(id) ON DELETE CASCADE,
    snapshot JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS command_post_voice_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES command_post_sessions(id) ON DELETE CASCADE,
    clip_id TEXT NOT NULL,
    report_id TEXT,
    origin TEXT NOT NULL,
    codec SMALLINT NOT NULL,
    content_type TEXT NOT NULL,
    audio BYTEA NOT NULL,
    transcript TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, clip_id)
);
CREATE INDEX IF NOT EXISTS idx_voice_session ON command_post_voice_messages(session_id);
"""


class SessionDatabase:
    def __init__(self) -> None:
        self.url = os.getenv("DATABASE_URL", "").strip()
        self.required = os.getenv("SANKAT_DATABASE_REQUIRED", "false").lower() == "true"
        self.session_id = str(uuid.uuid4())
        self.started_at = datetime.now(timezone.utc)
        self.pool: asyncpg.Pool | None = None
        self.error: str | None = None

    @property
    def enabled(self) -> bool:
        return self.pool is not None

    async def start(self) -> None:
        if not self.url:
            self.error = "DATABASE_URL is not configured"
            if self.required:
                raise RuntimeError(self.error)
            print(f"[database] {self.error}; session history is disabled")
            return
        try:
            self.pool = await asyncpg.create_pool(self.url, min_size=1, max_size=5,
                                                  command_timeout=10, timeout=5)
            async with self.pool.acquire() as conn:
                await conn.execute(SCHEMA)
                await conn.execute(
                    "INSERT INTO command_post_sessions(id, started_at, host) VALUES($1,$2,$3)",
                    uuid.UUID(self.session_id), self.started_at, socket.gethostname(),
                )
            self.error = None
            print(f"[database] new blank session {self.session_id}")
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            if self.required:
                raise RuntimeError("PostgreSQL session startup failed") from exc
            print(f"[database] unavailable ({self.error}); session history is disabled")
            self.pool = None

    async def close(self) -> None:
        if self.pool is None:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE command_post_sessions SET ended_at=now() WHERE id=$1",
                uuid.UUID(self.session_id),
            )
        await self.pool.close()
        self.pool = None

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.enabled,
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            # Detailed driver/network errors stay in server logs (rule #10).
            "error": "unavailable" if self.error else None,
        }

    async def persist_snapshot(self, snapshot: dict[str, Any]) -> None:
        if self.pool is None:
            return
        payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO command_post_snapshots(session_id, snapshot, updated_at)
                   VALUES($1,$2::jsonb,now())
                   ON CONFLICT(session_id) DO UPDATE
                   SET snapshot=excluded.snapshot, updated_at=now()""",
                uuid.UUID(self.session_id), payload,
            )

    async def store_voice(self, *, clip_id: str, report_id: str | None, origin: str,
                          codec: int, content_type: str, audio: bytes,
                          transcript: str | None = None) -> None:
        if self.pool is None:
            raise RuntimeError("PostgreSQL is unavailable")
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO command_post_voice_messages
                   (session_id,clip_id,report_id,origin,codec,content_type,audio,transcript)
                   VALUES($1,$2,$3,$4,$5,$6,$7,$8)
                   ON CONFLICT(session_id,clip_id) DO UPDATE SET
                     report_id=excluded.report_id, content_type=excluded.content_type,
                     audio=excluded.audio,
                     transcript=COALESCE(excluded.transcript,command_post_voice_messages.transcript)""",
                uuid.UUID(self.session_id), clip_id, report_id, origin, codec,
                content_type, audio, transcript,
            )

    async def get_voice(self, clip_id: str) -> tuple[bytes, str] | None:
        return await self.get_session_voice(self.session_id, clip_id)

    async def get_session_voice(self, session_id: str, clip_id: str) -> tuple[bytes, str] | None:
        if self.pool is None:
            return None
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT audio,content_type FROM command_post_voice_messages
                   WHERE session_id=$1 AND clip_id=$2""",
                sid, clip_id,
            )
        return (bytes(row["audio"]), row["content_type"]) if row else None

    async def list_sessions(self) -> list[dict[str, Any]]:
        if self.pool is None:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT s.id,s.started_at,s.ended_at,
                          COALESCE(jsonb_array_length(p.snapshot->'incidents'),0) AS incidents,
                          (SELECT count(*) FROM command_post_voice_messages v
                           WHERE v.session_id=s.id) AS voices
                   FROM command_post_sessions s
                   LEFT JOIN command_post_snapshots p ON p.session_id=s.id
                   ORDER BY s.started_at DESC LIMIT 100"""
            )
        return [dict(row) for row in rows]

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        if self.pool is None:
            return None
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT s.id,s.started_at,s.ended_at,p.snapshot
                   FROM command_post_sessions s
                   LEFT JOIN command_post_snapshots p ON p.session_id=s.id
                   WHERE s.id=$1""", sid,
            )
        if row is None:
            return None
        result = dict(row)
        if isinstance(result.get("snapshot"), str):
            result["snapshot"] = json.loads(result["snapshot"])
        return result


database = SessionDatabase()
