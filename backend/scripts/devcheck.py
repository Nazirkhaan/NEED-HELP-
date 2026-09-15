"""One-command stack health check: DB -> backend -> demo login -> frontend.

Run from backend/:
    python scripts/devcheck.py
Exit code 0 = every layer green. Useful right before a demo.

Override endpoints via env vars: BACKEND_URL (default http://127.0.0.1:8000),
FRONTEND_URL (default http://localhost:3000). The DB target comes from
backend/.env (DATABASE_URL) via the app's own settings + conninfo resolution.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db.pool import _resolve_conninfo  # noqa: E402

BACKEND = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
FRONTEND = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
DEMO_EMAIL = "student.demo@sih.gov.in"
DEMO_PASSWORD = "demo1234"

failures: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {detail}")
    if not ok:
        failures.append(name)


def http(url: str, method: str = "GET", body: dict | None = None,
         token: str | None = None, timeout: float = 8.0):
    # Loopback checks must never go through a proxy (on Windows, urllib picks
    # up the system/registry proxy settings; curl does not).
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    def _parse(raw: bytes) -> dict:
        try:
            return json.loads(raw.decode() or "{}")
        except Exception:
            # Non-JSON body (e.g. the frontend's HTML index) — still a response.
            return {"_body": raw.decode(errors="replace")[:80]}

    try:
        with opener.open(req, timeout=timeout) as res:
            return res.status, _parse(res.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, _parse(exc.read())
        except Exception:
            return exc.code, {}
    except Exception as exc:
        return 0, {"_error": str(exc)}


def main() -> int:
    print(f"devcheck — backend={BACKEND} frontend={FRONTEND}\n")

    # 1. Database (the Podman PG16 + pgvector container published on 5433)
    try:
        import psycopg

        conn = psycopg.connect(_resolve_conninfo(settings.database_url),
                               connect_timeout=5, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("select version()")
            version = cur.fetchone()[0].split(",")[0]
            cur.execute("select 1 from pg_available_extensions where name='vector'")
            vector = cur.fetchone() is not None
            cur.execute("select count(*) from users where is_active")
            users = cur.fetchone()[0]
        conn.close()
        ok = "PostgreSQL 16" in version and vector
        check("database", ok, f"{version} | pgvector={vector} | active_users={users}")
        if not ok:
            print("      expected PostgreSQL 16 with pgvector (the Podman DB on :5433)")
    except Exception as exc:
        check("database", False, f"unreachable: {str(exc).strip()[:120]}")

    # 2. Backend process + its own DB view
    status, body = http(f"{BACKEND}/api/health")
    check("backend health", status == 200 and body.get("status") == "ok"
          and body.get("db") is True,
          f"HTTP {status} {json.dumps(body)[:120]}")

    # 3. Demo login + /api/auth/me (regression: rbac.py must return display_name)
    status, body = http(f"{BACKEND}/api/auth/login", "POST",
                        {"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    token = body.get("access_token")
    check("demo login", status == 200 and bool(token),
          f"HTTP {status} {'token received' if token else json.dumps(body)[:120]}")
    if token:
        status, me = http(f"{BACKEND}/api/auth/me", token=token)
        ok = status == 200 and me.get("role") == "student" and bool(me.get("role_display"))
        check("auth/me (rbac)", ok, f"HTTP {status} role={me.get('role')} "
              f"display={me.get('role_display')}")

    # 4. Frontend dev server
    status, body = http(FRONTEND)
    check("frontend", 200 <= status < 400,
          f"HTTP {status} {json.dumps(body)[:120] if body else ''}")

    print()
    if failures:
        print(f"devcheck FAILED: {', '.join(failures)}")
        print("hints: podman-compose up -d (DB) ; python run.py (backend) ; "
              "npm run dev -- -p 3000 (frontend)")
        return 1
    print("devcheck PASSED — all four layers green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
