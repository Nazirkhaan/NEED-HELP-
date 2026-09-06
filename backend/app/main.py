"""FastAPI application factory."""
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # ensure 'seed' importable

from app.api import admin, auth, industry, jobs, meta, student, tpo  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.migrate import run_migrations  # noqa: E402
from app.db.pool import execute, fetch_one, get_pool  # noqa: E402
from app.services.config_loader import roles_config  # noqa: E402


def ensure_roles() -> None:
    """Upsert roles from configs/roles.json — RBAC is config-driven."""
    for role in roles_config():
        row = fetch_one(
            "select id from roles_permissions where name = %s", (role["name"],)
        )
        import json

        if row is None:
            execute(
                """
                insert into roles_permissions (name, display_name, permissions, description)
                values (%s, %s, %s::jsonb, %s)
                """,
                (role["name"], role["display_name"],
                 json.dumps(role["permissions"]), role.get("description")),
            )
        else:
            # keep DB permissions unless an admin edited them (audit log wins)
            audited = fetch_one(
                "select id from rbac_audit_log where role_id = %s limit 1", (row["id"],)
            )
            if audited is None:
                execute(
                    "update roles_permissions set permissions = %s::jsonb where id = %s",
                    (json.dumps(role["permissions"]), row["id"]),
                )


app = FastAPI(
    title="SIH26044 — Academia-Industry Collaboration Portal",
    description="Skill mapping, internships & placement MVP (hackathon build). "
                "All seeded data is synthetic and labelled as such in the UI.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(student.router)
app.include_router(jobs.router)
app.include_router(industry.router)
app.include_router(tpo.router)
app.include_router(admin.router)


@app.on_event("startup")
def startup() -> None:
    get_pool()  # fail fast if DB is unreachable
    applied = run_migrations()
    if applied:
        print(f"[startup] applied migrations: {applied}")
    ensure_roles()


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "db": True,
        "provider": None,  # filled below lazily
    }


@app.get("/api/health/detail")
def health_detail():
    from app.services import embeddings

    return {
        "status": "ok",
        "embedding_provider": embeddings.provider_name(),
        "database_url_set": bool(settings.database_url),
    }
