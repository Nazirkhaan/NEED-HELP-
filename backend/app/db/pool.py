"""Shared psycopg3 connection pool.

Works with local Postgres (Podman/Docker) and managed providers (Neon, Supabase).
For Neon: use a direct (non-pooled) connection string with ?sslmode=require.
"""
import contextlib

# pyrefly: ignore [missing-import]
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import settings

_pool: AsyncConnectionPool | None = None


def _resolve_conninfo(conninfo: str) -> str:
    """Normalize connection string for the runtime environment.

    - Local (Podman/Docker on Windows): replace localhost with 127.0.0.1
      to avoid IPv6 resolution timeouts on WSL2.
    - Neon / remote hosts: returned unchanged (sslmode=require is in the URL).
    """
    if "@localhost:" in conninfo:
        return conninfo.replace("@localhost:", "@127.0.0.1:")
    if "@localhost/" in conninfo:
        return conninfo.replace("@localhost/", "@127.0.0.1/")
    return conninfo


def _is_neon(conninfo: str) -> bool:
    """Detect if the target is a Neon managed database."""
    return "neon.tech" in conninfo


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        conninfo = _resolve_conninfo(settings.database_url)
        neon = _is_neon(conninfo)
        _pool = ConnectionPool(
            conninfo=conninfo,
            # Neon free tier: keep min_size=1 to avoid holding idle connections
            # against the 100-connection limit. Local: min_size=2 is fine.
            min_size=1 if neon else 2,
            max_size=10 if neon else 20,
            # Neon cold start (compute wake) can take 1-3s; 30s timeout is safe.
            timeout=30.0 if neon else 10.0,
            max_waiting=50,
            kwargs={"row_factory": dict_row, "autocommit": True},
            open=True,
        )
    return _pool


def fetch_all(sql: str, params: tuple | dict = ()) -> list[dict]:
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def fetch_one(sql: str, params: tuple | dict = ()) -> dict | None:
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def execute(sql: str, params: tuple | dict = ()) -> dict | None:
    """Execute a write statement, returning RETURNING row if present."""
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone() if cur.description else None


@contextlib.contextmanager
def transaction():
    """Context manager yielding a cursor; commits on success, rolls back on error."""
    with get_pool().connection() as conn:
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
