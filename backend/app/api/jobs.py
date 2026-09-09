"""Shared job-descriptions listing (any authenticated user may browse open jobs)."""
from fastapi import APIRouter, Depends, HTTPException

from app.core.rbac import AuthUser, get_current_user
from app.db.pool import afetch_all, afetch_one

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(stream: str | None = None, user: AuthUser = Depends(get_current_user)):
    if stream:
        rows = await afetch_all(
            """
            select jd.id, jd.title, jd.kind, jd.stream, jd.location, jd.stipend,
                   jd.salary_min, jd.salary_max, jd.seats, jd.status,
                   jd.extracted_skills, o.name as organization_name, jd.created_at
            from job_descriptions jd join organizations o on o.id = jd.organization_id
            where jd.stream = %s and jd.status = 'open'
            order by jd.created_at desc
            """,
            (stream,),
        )
    else:
        rows = await afetch_all(
            """
            select jd.id, jd.title, jd.kind, jd.stream, jd.location, jd.stipend,
                   jd.salary_min, jd.salary_max, jd.seats, jd.status,
                   jd.extracted_skills, o.name as organization_name, jd.created_at
            from job_descriptions jd join organizations o on o.id = jd.organization_id
            where jd.status = 'open'
            order by jd.created_at desc
            """
        )
    for r in rows:
        r["id"] = str(r["id"])
        r["n_skills"] = len(r.pop("extracted_skills") or [])
    return rows


@router.get("/{jd_id}")
async def job_detail(jd_id: str, user: AuthUser = Depends(get_current_user)):
    row = await afetch_one(
        """
        select jd.*, o.name as organization_name
        from job_descriptions jd join organizations o on o.id = jd.organization_id
        where jd.id = %s
        """,
        (jd_id,),
    )
    if row is None:
        raise HTTPException(404, "Job not found")
    row["id"] = str(row["id"])
    return row
