"""FastAPI application factory."""
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # ensure 'seed' importable

from app.api import admin, auth, industry, jobs, meta, student, tpo  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.migrate import run_migrations  # noqa: E402
from app.db.pool import afetch_one, aexecute, get_async_pool  # noqa: E402
from app.services.config_loader import roles_config  # noqa: E402


async def ensure_roles() -> None:
    """Upsert roles from configs/roles.json — RBAC is config-driven."""
    import json

    for role in roles_config():
        row = await afetch_one(
            "select id from roles_permissions where name = %s", (role["name"],)
        )
        if row is None:
            await aexecute(
                """
                insert into roles_permissions (name, display_name, permissions, description)
                values (%s, %s, %s::jsonb, %s)
                """,
                (role["name"], role["display_name"],
                 json.dumps(role["permissions"]), role.get("description")),
            )
        else:
            # keep DB permissions unless an admin edited them (audit log wins)
            audited = await afetch_one(
                "select id from rbac_audit_log where role_id = %s limit 1", (row["id"],)
            )
            if audited is None:
                await aexecute(
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
async def startup() -> None:
    # fail fast if the DB is unreachable; the async pool stays open for the
    # process lifetime (retries + per-checkout health check configured)
    await get_async_pool()
    applied = run_migrations()  # sync script path; startup-time only
    if applied:
        print(f"[startup] applied migrations: {applied}")
    await ensure_roles()


@app.get("/api/health")
async def health():
    db_ok = bool(await afetch_one("select 1 as ok"))
    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "provider": None,  # filled below lazily
    }


@app.get("/api/health/detail")
async def health_detail():
    from app.services import embeddings

    return {
        "status": "ok",
        "embedding_provider": embeddings.provider_name(),
        "database_url_set": bool(settings.database_url),
    }
