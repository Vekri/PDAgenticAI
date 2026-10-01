"""SQLite audit log stored on this PC."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.config import DB_PATH
from app.schemas import DecisionResult


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _run(path: Path, fn):
    connection = _connect(path)
    try:
        with connection:
            return fn(connection)
    finally:
        connection.close()


def ensure_db(path: Path | None = None) -> Path:
    target = path or DB_PATH
    _run(
        target,
        lambda connection: connection.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                business_name TEXT,
                recommendation TEXT,
                pd_score REAL,
                payload TEXT NOT NULL
            )
            """
        ),
    )
    return target


def save_decision(result: DecisionResult, path: Path | None = None) -> None:
    target = ensure_db(path)
    payload = result.model_dump()
    _run(
        target,
        lambda connection: connection.execute(
            """
            INSERT OR REPLACE INTO decisions
            (run_id, created_at, business_name, recommendation, pd_score, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result.run_id,
                result.created_at,
                result.application.get("business_name"),
                result.recommendation,
                result.pd_score,
                json.dumps(payload),
            ),
        ),
    )


def list_decisions(limit: int = 20, path: Path | None = None) -> list[dict]:
    target = path or DB_PATH
    if not target.exists():
        return []
    ensure_db(target)
    return _run(
        target,
        lambda connection: [
            dict(row)
            for row in connection.execute(
                """
                SELECT run_id, created_at, business_name, recommendation, pd_score
                FROM decisions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ],
    )


def get_decision(run_id: str, path: Path | None = None) -> dict | None:
    target = path or DB_PATH
    if not target.exists():
        return None
    ensure_db(target)
    def _read(connection: sqlite3.Connection) -> str | None:
        row = connection.execute("SELECT payload FROM decisions WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return row["payload"]

    payload = _run(target, _read)
    if payload is None:
        return None
    return json.loads(payload)


def clear_decisions(path: Path | None = None) -> None:
    target = path or DB_PATH
    if target.exists():
        target.unlink()
