"""Async-first psycopg3 connection pool (Phase 1, Deliverable 1).

The app runtime (API routes + services) uses the AsyncConnectionPool with:
  - bounded size (min 2 / max 20),
  - per-checkout health check (SELECT 1) via psycopg_pool's `check`,
  - automatic retry with backoff on transient acquisition/connection errors.

The sync helpers below are a *script-only* fallback (seed, walkthrough,
migrations, benchmarks) so standalone CLI processes don't need an event loop.
App runtime code must never import them.
"""
import asyncio
import contextlib
import sys

# psycopg async mode requires a SelectorEventLoop; Windows defaults to
# ProactorEventLoop. Affects every loop created AFTER this import (scripts,
# uvicorn when launched via run.py). Servers started via the bare uvicorn CLI
# create their loop before importing the app -- use backend/run.py instead.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# pyrefly: ignore [missing-import]
from psycopg import OperationalError
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, ConnectionPool, PoolTimeout

from app.config import settings

POOL_MIN = 2
POOL_MAX = 20
ACQUIRE_TIMEOUT_S = 10.0
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_S = 0.25

_async_pool: AsyncConnectionPool | None = None
_async_pool_loop: asyncio.AbstractEventLoop | None = None
_sync_pool: ConnectionPool | None = None

# Transient = failed before the statement could complete reliably; safe to
# retry an INSERT here would risk double-execution only if the server actually
# committed and we lost the connection mid-response, which autocommit SELECT
# traffic (this app) and the ON CONFLICT upserts make benign.
_TRANSIENT_ERRORS = (PoolTimeout, OperationalError)


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


# ---------------------------------------------------------------- async pool

async def get_async_pool() -> AsyncConnectionPool:
    """Shared async pool. Recreated if the running loop changed (scripts)."""
    global _async_pool, _async_pool_loop
    loop = asyncio.get_running_loop()
    if _async_pool is not None and (_async_pool.closed or _async_pool_loop is not loop):
        with contextlib.suppress(Exception):
            await _async_pool.close(timeout=2.0)
        _async_pool = None
    if _async_pool is None:
        conninfo = _resolve_conninfo(settings.database_url)
        neon = _is_neon(conninfo)
        _async_pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=1 if neon else POOL_MIN,
            max_size=10 if neon else POOL_MAX,
            timeout=ACQUIRE_TIMEOUT_S,
            max_waiting=50,
            # DoD: per-checkout health check (SELECT 1) — a broken connection
            # is replaced transparently instead of handing a dead socket up.
            check=AsyncConnectionPool.check_connection,
            reconnect_timeout=ACQUIRE_TIMEOUT_S,
            kwargs={"row_factory": dict_row, "autocommit": True},
            open=False,
        )
        await _async_pool.open(wait=True, timeout=ACQUIRE_TIMEOUT_S)
        _async_pool_loop = loop
    return _async_pool


async def _with_retry(op):
    last: Exception | None = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return await op()
        except _TRANSIENT_ERRORS as exc:
            last = exc
            await asyncio.sleep(RETRY_BACKOFF_S * (attempt + 1))
    raise last  # type: ignore[misc]


async def afetch_all(sql: str, params: tuple | dict = ()) -> list[dict]:
    pool = await get_async_pool()

    async def run() -> list[dict]:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchall()

    return await _with_retry(run)


async def afetch_one(sql: str, params: tuple | dict = ()) -> dict | None:
    pool = await get_async_pool()

    async def run() -> dict | None:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchone()

    return await _with_retry(run)


async def aexecute(sql: str, params: tuple | dict = ()) -> dict | None:
    """Execute a write statement, returning RETURNING row if present."""
    pool = await get_async_pool()

    async def run() -> dict | None:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchone() if cur.description else None

    return await _with_retry(run)


@contextlib.asynccontextmanager
async def atransaction():
    """Async context manager yielding a cursor; commits on success, rolls back on error."""
    pool = await get_async_pool()
    conn = await _with_retry(pool.getconn)  # getconn runs the checkout health check
    try:
        async with conn:
            try:
                async with conn.cursor() as cur:
                    yield cur
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
    finally:
        await pool.putconn(conn)


# ---------------------------------------------------------------- script-only

def get_pool() -> ConnectionPool:
    """Sync pool for standalone scripts (seed/walkthrough/migrate/bench)."""
    global _sync_pool
    if _sync_pool is None or _sync_pool.closed:
        conninfo = _resolve_conninfo(settings.database_url)
        neon = _is_neon(conninfo)
        _sync_pool = ConnectionPool(
            conninfo=conninfo,
            min_size=1 if neon else 2,
            max_size=10 if neon else 20,
            timeout=ACQUIRE_TIMEOUT_S,
            max_waiting=50,
            check=ConnectionPool.check_connection,
            kwargs={"row_factory": dict_row, "autocommit": True},
            open=True,
        )
    return _sync_pool


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


def run_async(coro):
    """Entry point for scripts that call async app code (one loop per call)."""
    return asyncio.run(coro)
