# Phase 1 Acceptance Criteria — "Stable Enough" Bar (Ratified)

**Status:** Ratified 2026-09-08 · **Scope:** Pool Hardening · HNSW Indexing · Compose Healthchecks
**Validated against:** live stack (`pgvector/pg16` via Podman, seeded synthetic data, Python 3.12)

## The Bar

Phase 1 is done when **all** of the following hold, measured by `backend/scripts/acceptance_bench.py`:

| # | Criterion | Target | Measured (this stack) | Verdict |
|---|-----------|--------|----------------------|---------|
| A1 | Vector top-5 cosine lookup latency (HNSW index scan) | < 20 ms | 0.30–0.90 ms | ✅ 22–66× headroom |
| A2 | Latency at 100k realistic vectors (HNSW) | < 20 ms | 0.53 ms median / 1.21 ms p95 | ✅ 16× headroom |
| A3 | True linear scan at 100k (control — proves A2 is index-driven) | reference | 63.0 ms median / 72.4 ms p95 | HNSW ≈ 119× faster |
| B1 | Pool errors under 50 concurrent clients × 20 requests | 0 timeouts / 0 errors | 0 / 1000 | ✅ |
| B2 | End-to-end request latency under that load | informational | p50 ≈ 24 ms, p95 ≈ 43 ms (2 queries/req, client-side threading included) | ✅ no event-loop starvation symptoms |
| B3 | Connection discipline | never exceeds `max_size`; server-side count returns to baseline after processes exit | plateaued at 20 (=`max_size`); ~0 remaining post-exit | ✅ no leak |
| C1 | Compose readiness gate | app blocked until `pg_isready` passes; unhealthy state visible | implemented in `podman-compose.yml` healthcheck | ✅ |

## Ratified Load Assumptions

- **Concurrent-user definition of "stable":** 50 concurrent DB clients is the Phase 1 ceiling (hackathon demo + judging load ≪ this).
- **Latency target:** sub-20 ms per vector lookup at the DB level. End-to-end HTTP latency is *not* part of this bar.

## Known Honest Caveats (do not hide from evaluators)

1. **At seed scale (~20 rows) the planner rightly ignores HNSW** — a seq scan of 19 rows is cheaper than any index. HNSW passes A1 because even a scan is trivially fast at that size. The index earns its keep from ~10k rows upward.
2. **The 119× crossover (A3) was measured on real-embedding-derived data** (seeded vectors + Gaussian perturbation). On fully random 384-dim vectors HNSW can *lose* to a seq scan — random data is the pathological case for graph ANN. Real embeddings are clustered; benchmarks must use realistic vectors.
3. **Parallel query workers can mask seq-scan cost** in EXPLAIN wall-time. Benchmarks that compare scan strategies should set `max_parallel_workers_per_gather = 0` and force the scan type explicitly.
4. **`app/db/pool.py` currently exposes a sync `ConnectionPool`** to all callers; the async-native refactor (import in place, callers pending) remains open Phase 1 engineering work. B1–B3 were measured against the sync pool with thread offloading.

## Reproduce

```bash
cd backend
.venv/Scripts/python.exe -m scripts.acceptance_bench   # A1, B1–B3
# A2/A3: see scripts/acceptance_bench.py header for the 100k-row procedure
```
