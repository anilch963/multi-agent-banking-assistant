"""Thin sqlite3 helpers. Swap this module to move to PostgreSQL."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from app import config


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def query(sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | dict = ()) -> int:
    """Run a write statement and return lastrowid."""
    with connect() as conn:
        return conn.execute(sql, params).lastrowid


def customer_exists(customer_id: str) -> bool:
    return query_one("SELECT 1 AS ok FROM customers WHERE customer_id = ?", (customer_id,)) is not None
