"""Industry endpoints: post JDs, review applicants with skill-diff, log
outcomes (triggers recalibration), verify student skills."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.rbac import AuthUser, require_perm
from app.db.pool import aexecute, afetch_all, afetch_one
from app.services import matching
from app.services.profile_pipeline import process_job_description
from app.services.recalibration import apply_outcome_recalibration
from app.services.verification import verify as verify_transition

router = APIRouter(prefix="/api/industry", tags=["industry"])


class JobBody(BaseModel):
    title: str
    kind: str = "internship"
    stream: str = "cse"
    description: str
    location: str | None = None
    stipend: int | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    seats: int = 1


class StatusBody(BaseModel):
    status: str


class OutcomeBody(BaseModel):
    application_id: str
    result: str  # completed | dropped | hired
    performance_rating: int | None = None
    industry_feedback: str | None = None


class VerifyBody(BaseModel):
    student_skill_id: str
    note: str | None = None


def _own_org(user: AuthUser) -> dict:
    if not user.organization_id:
        raise HTTPException(400, "Industry account has no organization linked")
    return {"organization_id": user.organization_id}


@router.get("/jobs")
async def my_jobs(user: AuthUser = Depends(require_perm("jobs.manage.own"))):
    org = _own_org(user)
    return await afetch_all(
        """
        select jd.id, jd.title, jd.kind, jd.stream, jd.status, jd.location,
               jd.stipend, jd.salary_min, jd.salary_max, jd.seats, jd.created_at,
               jd.extracted_skills,
               (select count(*) from applications a where a.job_description_id = jd.id) as applicant_count
        from job_descriptions jd
        where jd.organization_id = %s
        order by jd.created_at desc
        """,
        (org["organization_id"],),
    )


@router.post("/jobs")
async def post_job(body: JobBody, user: AuthUser = Depends(require_perm("jobs.manage.own"))):
    org = _own_org(user)
    if body.kind not in ("internship", "placement"):
        raise HTTPException(400, "kind must be internship or placement")
    if len(body.description.strip()) < 40:
        raise HTTPException(400, "Description too short for meaningful skill extraction")
    row = await aexecute(
        """
        insert into job_descriptions
            (organization_id, posted_by_user_id, title, kind, stream, description,
             location, stipend, salary_min, salary_max, seats, is_synthetic)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false)
        returning id
        """,
        (org["organization_id"], user.id, body.title, body.kind, body.stream,
         body.description, body.location, body.stipend, body.salary_min,
         body.salary_max, body.seats),
    )
    jd_id = str(row["id"])
    pipeline = await process_job_description(jd_id)
    return {"job_description_id": jd_id, **pipeline}


@router.get("/jobs/{jd_id}/applicants")
async def applicants(jd_id: str, user: AuthUser = Depends(require_perm("applicants.view.own"))):
    jd = await afetch_one("select * from job_descriptions where id = %s", (jd_id,))
    if jd is None or str(jd["organization_id"]) != user.organization_id:
        raise HTTPException(404, "Job not found in your organization")
    rows = await afetch_all(
        """
        select a.id as application_id, a.status, a.applied_at, a.cover_note,
               sp.id as student_profile_id, sp.cgpa, sp.graduation_year, sp.stream,
               u.full_name, i.name as institution_name,
               m.id as match_id, m.score, m.semantic_score, m.taxonomy_score,
               m.provider, m.matched_skills, m.missing_skills, m.extra_skills,
               m.literal_keyword_overlap,
               o.id as outcome_id
        from applications a
        join student_profiles sp on sp.id = a.student_profile_id
        join users u on u.id = sp.user_id
        left join institutions i on i.id = sp.institution_id
        left join matches m on m.id = a.match_id
        left join outcomes o on o.application_id = a.id
        where a.job_description_id = %s
        order by m.score desc nulls last
        """,
        (jd_id,),
    )
    for r in rows:
        r["application_id"] = str(r["application_id"])
        r["student_profile_id"] = str(r["student_profile_id"])
        r["score"] = float(r["score"]) if r["score"] is not None else None
    return rows


@router.post("/applications/{application_id}/status")
async def set_application_status(application_id: str, body: StatusBody,
                                 user: AuthUser = Depends(require_perm("applications.review.own"))):
    app_row = await afetch_one("select * from applications where id = %s", (application_id,))
    if app_row is None:
        raise HTTPException(404, "Application not found")
    jd = await afetch_one("select organization_id from job_descriptions where id = %s",
                          (app_row["job_description_id"],))
    if str(jd["organization_id"]) != user.organization_id:
        raise HTTPException(403, "Not your organization's job")
    if body.status not in ("applied", "shortlisted", "selected", "rejected"):
        raise HTTPException(400, "invalid status")
    await aexecute(
        "update applications set status = %s, updated_at = now() where id = %s",
        (body.status, application_id),
    )
    return {"application_id": application_id, "status": body.status}


@router.post("/outcomes")
async def log_outcome(body: OutcomeBody, user: AuthUser = Depends(require_perm("outcomes.log.own"))):
    app_row = await afetch_one("select * from applications where id = %s", (body.application_id,))
    if app_row is None:
        raise HTTPException(404, "Application not found")
    jd = await afetch_one("select * from job_descriptions where id = %s", (app_row["job_description_id"],))
    if str(jd["organization_id"]) != user.organization_id:
        raise HTTPException(403, "Not your organization's application")
    if body.result not in ("completed", "dropped", "hired"):
        raise HTTPException(400, "result must be completed | dropped | hired")
    if body.performance_rating is not None and not 1 <= body.performance_rating <= 5:
        raise HTTPException(400, "rating must be 1..5")
    existing = await afetch_one("select id from outcomes where application_id = %s", (body.application_id,))
    if existing:
        raise HTTPException(409, "Outcome already logged for this application")
    row = await aexecute(
        """
        insert into outcomes (application_id, job_description_id, student_profile_id,
            result, performance_rating, industry_feedback, logged_by_user_id)
        values (%s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (body.application_id, app_row["job_description_id"], app_row["student_profile_id"],
         body.result, body.performance_rating, body.industry_feedback, user.id),
    )
    result = await apply_outcome_recalibration(str(row["id"]))
    return {"outcome_id": str(row["id"]), **result}


@router.get("/students/{student_profile_id}/skills")
async def student_skills(student_profile_id: str,
                         user: AuthUser = Depends(require_perm("skills.verify.industry"))):
    """Skills of a student who applied to this org, for the verify action."""
    applied = await afetch_one(
        """
        select 1 from applications a
        join job_descriptions jd on jd.id = a.job_description_id
        where a.student_profile_id = %s and jd.organization_id = %s
        limit 1
        """,
        (student_profile_id, user.organization_id),
    )
    if applied is None:
        raise HTTPException(403, "Student has not applied to your organization")
    return await afetch_all(
        """
        select v.id, v.state, v.cosigned_note, v.verified_note, v.cosigned_at, v.verified_at,
               s.code, s.label, s.category
        from skill_verification_state v join skills s on s.id = v.skill_id
        where v.student_profile_id = %s order by s.category, s.label
        """,
        (student_profile_id,),
    )


@router.post("/verify-skill")
async def verify_skill(body: VerifyBody, user: AuthUser = Depends(require_perm("skills.verify.industry"))):
    row = await verify_transition(body.student_skill_id, {"id": user.id}, body.note)
    # verification changes the credit a skill earns -> refresh that student's matches
    await matching.compute_matches_for_student(str(row["student_profile_id"]))
    return {
        "student_skill_id": str(row["id"]),
        "state": row["state"],
        "note": "Matches recomputed: verified skills earn full credit in match scoring.",
    }
