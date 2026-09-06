"""Minimal ordered SQL migration runner.

Applies every .sql file in backend/migrations in filename order, exactly once,
tracked in the schema_migrations table.
"""
import sys
from pathlib import Path

from app.config import BASE_DIR
from app.db.pool import get_pool

MIGRATIONS_DIR = BASE_DIR / "migrations"


def run_migrations() -> list[str]:
    applied: list[str] = []
    with get_pool().connection() as conn:
        conn.execute(
            """
            create table if not exists schema_migrations (
                filename text primary key,
                applied_at timestamptz not null default now()
            )
            """
        )
        done = {
            r["filename"]
            for r in conn.execute(
                "select filename from schema_migrations"
            ).fetchall()
        }
        files = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))
        for name in files:
            if name in done:
                continue
            sql = (MIGRATIONS_DIR / name).read_text(encoding="utf-8")
            conn.execute(sql)
            conn.execute(
                "insert into schema_migrations(filename) values (%s)", (name,)
            )
            applied.append(name)
    return applied


if __name__ == "__main__":
    ran = run_migrations()
    print(f"Applied {len(ran)} migration(s): {ran or 'none (up to date)'}")
    sys.exit(0)
