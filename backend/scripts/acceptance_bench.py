"""Phase 1 acceptance benchmark: vector-search latency + pool stability.

Ratifies the "stable enough" bar for Phase 1:
  A) Vector search latency < 20ms (HNSW vs forced linear scan).
  B) 50 concurrent clients against the shared ASYNC pool, all on one event
     loop: 0 PoolTimeout errors, no connection leaks, and the event loop stays
     responsive (loop-lag heartbeat stays well under one request latency).

Usage:  python -m scripts.acceptance_bench
"""
import asyncio
import statistics
import time

from app.config import settings
from app.db.pool import afetch_all, get_async_pool, get_pool

CONCURRENCY = 50
REQUESTS_PER_WORKER = 20
LATENCY_TARGET_MS = 20.0

VECTOR_QUERY = """
    SELECT id, title, 1 - (embedding <=> %s::vector) AS score
    FROM job_descriptions
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> %s::vector
    LIMIT 5
"""


async def _pick_query_vector_async() -> str:
    row = await afetch_all(
        "SELECT embedding::text FROM job_descriptions WHERE embedding IS NOT NULL LIMIT 1"
    )
    return row[0]["embedding"]


def _pick_query_vector() -> str:
    with get_pool().connection() as conn, conn.cursor() as cur:
        row = cur.execute(
            "SELECT embedding::text FROM job_descriptions WHERE embedding IS NOT NULL LIMIT 1"
        ).fetchone()
    return row["embedding"]


def bench_vector_scan(force_linear: bool) -> dict:
    """EXPLAIN ANALYZE the top-K cosine query, HNSW vs forced linear scan."""
    qv = _pick_query_vector()
    with get_pool().connection() as conn, conn.cursor() as cur:
        # At seed scale (~20 JDs) the planner rightly prefers a seq scan; force
        # index usage so we measure actual HNSW latency, not a 19-row scan.
        if not force_linear:
            cur.execute("SET enable_seqscan = off")
        cur.execute(f"SET enable_indexscan = {'off' if force_linear else 'on'}")
        cur.execute("SET enable_bitmapscan = off")
        cur.execute("SET max_parallel_workers_per_gather = 0")
        cur.execute(
            "EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) " + VECTOR_QUERY,
            (qv, qv),
        )
        plan = cur.fetchone()["QUERY PLAN"][0]
        node = _find_node(plan["Plan"], "Index Scan") or _find_node(plan["Plan"], "Seq Scan")
        exec_ms = plan["Execution Time"]
        scan_type = node["Node Type"] if node else plan["Plan"]["Node Type"]
    return {"mode": "linear" if force_linear else "hnsw", "scan": scan_type, "ms": exec_ms}


def _find_node(plan: dict, node_type: str):
    if plan["Node Type"] == node_type:
        return plan
    for child in plan.get("Plans", []):
        found = _find_node(child, node_type)
        if found:
            return found
    return None


def _pg_connection_count() -> int:
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) c FROM pg_stat_activity WHERE datname = current_database()")
        return cur.fetchone()["c"]


async def bench_pool_stability() -> dict:
    """Hammer the async pool from one event loop with CONCURRENCY workers.

    A heartbeat task sleeps 10ms and records drift — drift is the true
    "event loop does not block" signal: if any DB call blocked the loop,
    drift would spike to the length of the blocking call.
    """
    qv = await _pick_query_vector_async()
    errors: list[str] = []
    latencies: list[float] = []
    loop_lags: list[float] = []

    async def heartbeat():
        while True:
            t0 = time.perf_counter()
            await asyncio.sleep(0.01)
            loop_lags.append((time.perf_counter() - t0) * 1000 - 10)

    hb = asyncio.create_task(heartbeat())

    async def worker(n: int):
        for _ in range(n):
            t0 = time.perf_counter()
            try:
                await afetch_all(VECTOR_QUERY, (qv, qv))
            except Exception as exc:  # noqa: BLE001 - count every failure mode
                errors.append(type(exc).__name__)
            latencies.append((time.perf_counter() - t0) * 1000)

    total_requests = CONCURRENCY * REQUESTS_PER_WORKER
    baseline_conns = _pg_connection_count()
    await asyncio.gather(*(worker(REQUESTS_PER_WORKER) for _ in range(CONCURRENCY)))
    await asyncio.sleep(1.0)
    hb.cancel()
    after_conns = _pg_connection_count()

    latencies.sort()
    return {
        "total_requests": total_requests,
        "errors": len(errors),
        "error_types": sorted(set(errors)),
        "p50_ms": round(statistics.median(latencies), 1),
        "p95_ms": round(latencies[int(len(latencies) * 0.95)], 1),
        "max_loop_lag_ms": round(max(loop_lags), 1) if loop_lags else None,
        "pg_conns_baseline": baseline_conns,
        "pg_conns_after": after_conns,
    }


def main() -> None:
    print(f"target db: {settings.database_url.split('@')[-1]}")
    for force in (False, True):
        r = bench_vector_scan(force_linear=force)
        verdict = "PASS" if r["ms"] < LATENCY_TARGET_MS else "FAIL"
        print(
            f"[vector/{r['mode']:6s}] scan={r['scan']:10s} "
            f"{r['ms']:.2f} ms  target<{LATENCY_TARGET_MS}ms  {verdict}"
        )
    r = asyncio.run(bench_pool_stability())
    leak = r["pg_conns_after"] - r["pg_conns_baseline"]
    print(
        f"[pool/{CONCURRENCY}x{REQUESTS_PER_WORKER} async] "
        f"errors={r['errors']}/{r['total_requests']} "
        f"({', '.join(r['error_types']) or 'none'})  p50={r['p50_ms']}ms  p95={r['p95_ms']}ms  "
        f"max_loop_lag={r['max_loop_lag_ms']}ms  "
        f"conns {r['pg_conns_baseline']}->{r['pg_conns_after']} (delta {leak:+d})"
    )
    print(
        "verdict:",
        "PASS" if (r["errors"] == 0 and r["p95_ms"] < 500
                   and r["max_loop_lag_ms"] is not None and r["max_loop_lag_ms"] < r["p95_ms"])
        else "FAIL",
        "(0 errors, p95 sane, loop-lag << request latency => loop not blocked)",
    )


if __name__ == "__main__":
    main()
