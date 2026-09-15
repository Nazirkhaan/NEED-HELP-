"""CLI: python -m seed --stream cse [--students 16] [--no-wipe] [--seed 42]

Taxonomy-only mode (skills + embeddings + learning resources, no synthetic
students/jobs):
    python -m seed --stream <key> --taxonomy-only
    python -m seed --stream all --taxonomy-only
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.migrate import run_migrations  # noqa: E402
from app.main import ensure_roles  # noqa: E402
from app.db.pool import get_async_pool  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic data seeder (SIH26044)")
    parser.add_argument("--stream", default="cse",
                        help="stream key from configs/ (cse, ece, ...) or 'all'")
    parser.add_argument("--students", type=int, default=16, dest="students_per_institution")
    parser.add_argument("--no-wipe", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--taxonomy-only", action="store_true",
                        help="upsert skills + embeddings + learning resources only, "
                             "without touching users/jobs/applications")
    args = parser.parse_args()

    await get_async_pool()
    applied = run_migrations()
    if applied:
        print(f"[migrations] applied {applied}")
    await ensure_roles()

    from app.services.config_loader import stream_keys
    from seed.generate import _embed_skills, _upsert_taxonomy, generate_stream

    if args.taxonomy_only:
        keys = stream_keys() if args.stream == "all" else [args.stream]
        if args.stream != "all" and args.stream not in keys:
            raise SystemExit(f"unknown stream '{args.stream}' (configs/streams.json)")
        for key in keys:
            cfg_path_note = f"taxonomy for stream '{key}'"
            try:
                n = await _upsert_taxonomy(key, _cfg(key))
            except FileNotFoundError as exc:
                print(f"[skip] {exc}")
                continue
            embedded = await _embed_skills(key)
            await aexecute_seed_run(key, cfg_path_note)
            print(f"[ok] {key}: {n} skills upserted, embeddings={'stored' if embedded else 'skipped'}")
        print(f"[done] taxonomy-only seed for {len(keys)} stream(s)")
        return

    if args.stream == "all":
        raise SystemExit("full seeding requires a single --stream value")
    summary = await generate_stream(
        args.stream,
        wipe=not args.no_wipe,
        students_per_institution=args.students_per_institution,
        seed=args.seed,
    )
    print(json_dumps(summary))


def _cfg(key: str) -> dict:
    import json
    from app.services.config_loader import stream_config
    return json.loads(json.dumps(stream_config(key)))


async def aexecute_seed_run(stream: str, note: str) -> None:
    from app.db.pool import aexecute
    await aexecute(
        "insert into seed_runs (stream, note, is_synthetic) values (%s, %s, true)",
        (stream, note),
    )


def json_dumps(obj) -> str:
    import json
    return json.dumps(obj, indent=2, default=str)


if __name__ == "__main__":
    asyncio.run(main())
