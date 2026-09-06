"""CLI: python -m seed --stream cse [--students 16] [--no-wipe] [--seed 42]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.migrate import run_migrations  # noqa: E402
from app.main import ensure_roles  # noqa: E402
from app.db.pool import get_pool  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic data seeder (SIH26044)")
    parser.add_argument("--stream", default="cse", help="stream key from configs/ (cse, ece, ...)")
    parser.add_argument("--students", type=int, default=16, dest="students_per_institution")
    parser.add_argument("--no-wipe", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    get_pool()
    applied = run_migrations()
    if applied:
        print(f"[migrations] applied {applied}")
    ensure_roles()

    from seed.generate import generate_stream

    summary = generate_stream(
        args.stream,
        wipe=not args.no_wipe,
        students_per_institution=args.students_per_institution,
        seed=args.seed,
    )
    print(json_dumps(summary))


def json_dumps(obj) -> str:
    import json
    return json.dumps(obj, indent=2, default=str)


if __name__ == "__main__":
    main()
