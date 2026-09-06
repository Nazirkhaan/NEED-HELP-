"""Student-facing endpoints: consent, profile/resume upload, claimed skills,
gap computation, explainable matches, applications."""
import io
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.rbac import AuthUser, get_current_user, require_perm
from app.db.pool import execute, fetch_all, fetch_one
from app.services import matching
from app.services.config_loader import stream_config
from app.services.gap import compute_role_gap, list_target_roles
from app.services.profile_pipeline import process_student_profile
from app.services.verification import claim, unclaim

router = APIRouter(prefix="/api/student", tags=["student"])


def _require_consent(user: AuthUser) -> None:
    if not user.consent_given:
        raise HTTPException(
            403,
            "DPDP consent required: grant data-processing consent before your "
            "profile can be stored or matched.",
        )


def _profile_or_404(user: AuthUser) -> dict:
    row = fetch_one(
        "select * from student_profiles where user_id = %s", (user.id,)
    )
    if row is None:
        raise HTTPException(404, "No student profile for this user")
    return row


def _extract_pdf_text(data: bytes) -> str | None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return None


@router.post("/consent")
def set_consent(body: dict, user: AuthUser = Depends(require_perm("consent.manage.own"))):
    granted = bool(body.get("granted"))
    execute(
        "update users set consent_given = %s, consent_at = case when %s then now() else null end "
        "where id = %s",
        (granted, granted, user.id),
    )
    return {"consent_given": granted}


@router.get("/profile")
def get_profile(user: AuthUser = Depends(require_perm("profile.manage.own"))):
    profile = _profile_or_404(user)
    skills = fetch_all(
        """
        select v.id, v.state, v.extracted_from_resume, v.claimed_at, v.cosigned_at,
               v.verified_at, v.cosigned_note, v.verified_note,
               s.id as skill_id, s.code, s.label, s.category, s.demand_weight
        from skill_verification_state v join skills s on s.id = v.skill_id
        where v.student_profile_id = %s order by s.category, s.label
        """,
        (str(profile["id"]),),
    )
    for s in skills:
        s["skill_id"] = str(s["skill_id"])
        s["id"] = str(s["id"])
        s["demand_weight"] = float(s["demand_weight"])
    inst = fetch_one(
        "select name from institutions where id = %s", (profile["institution_id"],)
    ) if profile["institution_id"] else None
    return {
        "profile": {
            **{k: (str(v) if k == "id" else v) for k, v in profile.items() if k != "embedding"},
            "institution_name": inst["name"] if inst else None,
        },
        "skills": skills,
    }


@router.post("/profile")
async def upload_profile(
    resume_text: str | None = Form(None),
    stream: str = Form("cse"),
    cgpa: float | None = Form(None),
    graduation_year: int | None = Form(None),
    bio: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: AuthUser = Depends(require_perm("profile.manage.own")),
):
    _require_consent(user)
    # DPDP: consent must be granted before we accept and process student data.
    if file is not None:
        data = await file.read()
        name = file.filename or "resume"
        if name.lower().endswith(".pdf"):
            text = _extract_pdf_text(data)
            if text is None:
                raise HTTPException(400, "Could not parse PDF; paste your resume text instead")
        else:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(400, "Unsupported file type; use .pdf or .txt or paste text")
        resume_text = (text or "").strip() or resume_text
    if not resume_text or not resume_text.strip():
        raise HTTPException(400, "Resume text (paste or .pdf/.txt upload) is required")

    existing = fetch_one("select id from student_profiles where user_id = %s", (user.id,))
    if existing:
        profile_id = str(existing["id"])
        execute(
            """
            update student_profiles set resume_text = %s, resume_file_name = %s,
                stream = %s, cgpa = %s, graduation_year = %s, bio = %s, updated_at = now()
            where id = %s
            """,
            (resume_text, file.filename if file else None, stream, cgpa,
             graduation_year, bio, profile_id),
        )
    else:
        row = execute(
            """
            insert into student_profiles
                (user_id, institution_id, stream, resume_text, resume_file_name,
                 cgpa, graduation_year, bio, consent_given, consent_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, case when %s then now() else null end)
            returning id
            """,
            (user.id, user.institution_id, stream, resume_text,
             file.filename if file else None, cgpa, graduation_year, bio,
             user.consent_given, user.consent_given),
        )
        profile_id = str(row["id"])
    result = process_student_profile(profile_id)
    return result


@router.get("/skills")
def my_skills(user: AuthUser = Depends(require_perm("skills.claim.own"))):
    profile = _profile_or_404(user)
    return fetch_all(
        """
        select v.id, v.state, s.code, s.label, s.category
        from skill_verification_state v join skills s on s.id = v.skill_id
        where v.student_profile_id = %s
        """,
        (str(profile["id"]),),
    )


@router.post("/skills")
def add_skill(body: dict, user: AuthUser = Depends(require_perm("skills.claim.own"))):
    _require_consent(user)
    profile = _profile_or_404(user)
    skill_id = body.get("skill_id")
    if not skill_id:
        raise HTTPException(400, "skill_id is required")
    skill = fetch_one("select id from skills where id = %s", (skill_id,))
    if skill is None:
        raise HTTPException(404, "unknown skill")
    row = claim(str(profile["id"]), skill_id, {"id": user.id}, extracted_from_resume=False)
    matching.compute_matches_for_student(str(profile["id"]))
    return {"student_skill_id": str(row["id"]), "state": row["state"]}


@router.delete("/skills/{student_skill_id}")
def remove_skill(student_skill_id: str, user: AuthUser = Depends(require_perm("skills.claim.own"))):
    profile = _profile_or_404(user)
    row = fetch_one(
        "select * from skill_verification_state where id = %s and student_profile_id = %s",
        (student_skill_id, str(profile["id"])),
    )
    if row is None:
        raise HTTPException(404, "skill claim not found")
    unclaim(student_skill_id, {"id": user.id})
    matching.compute_matches_for_student(str(profile["id"]))
    return {"removed": True}


@router.get("/target-roles")
def target_roles(user: AuthUser = Depends(require_perm("gap.view.own"))):
    profile = _profile_or_404(user)
    return list_target_roles(profile["stream"])


@router.get("/gap")
def gap(role: str, user: AuthUser = Depends(require_perm("gap.view.own"))):
    profile = _profile_or_404(user)
    try:
        return compute_role_gap(str(profile["id"]), role)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/matches")
def matches(user: AuthUser = Depends(require_perm("matches.view.own"))):
    profile = _profile_or_404(user)
    rows = matching.top_matches_for_student(str(profile["id"]), limit=50)
    out = []
    for r in rows:
        out.append({
            "match_id": str(r["id"]),
            "job_description_id": str(r["job_description_id"]),
            "title": r["title"], "kind": r["kind"], "location": r["location"],
            "stipend": r["stipend"], "salary_min": r["salary_min"], "salary_max": r["salary_max"],
            "organization_name": r["organization_name"], "stream": r["stream"],
            "score": float(r["score"]), "semantic_score": float(r["semantic_score"] or 0),
            "taxonomy_score": float(r["taxonomy_score"] or 0), "provider": r["provider"],
            "matched_skills": r["matched_skills"], "missing_skills": r["missing_skills"],
            "extra_skills": r["extra_skills"],
            "literal_keyword_overlap": float(r["literal_keyword_overlap"]),
            "application_id": str(r["application_id"]) if r["application_id"] else None,
            "application_status": r["application_status"],
        })
    return out


@router.post("/matches/refresh")
def refresh_matches(user: AuthUser = Depends(require_perm("matches.view.own"))):
    profile = _profile_or_404(user)
    n = matching.compute_matches_for_student(str(profile["id"]))
    return {"matches_computed": n}


@router.post("/applications")
def apply(body: dict, user: AuthUser = Depends(require_perm("applications.create.own"))):
    _require_consent(user)
    profile = _profile_or_404(user)
    jd_id = body.get("job_description_id")
    jd = fetch_one(
        "select * from job_descriptions where id = %s and status = 'open'", (jd_id,)
    )
    if jd is None:
        raise HTTPException(404, "Job not found or closed")
    existing = fetch_one(
        "select id from applications where student_profile_id = %s and job_description_id = %s",
        (str(profile["id"]), jd_id),
    )
    if existing:
        raise HTTPException(409, "You have already applied to this job")
    match = fetch_one(
        "select id from matches where student_profile_id = %s and job_description_id = %s",
        (str(profile["id"]), jd_id),
    )
    if match is None:
        matching.compute_matches_for_student(str(profile["id"]), jd_id=jd_id)
        match = fetch_one(
            "select id from matches where student_profile_id = %s and job_description_id = %s",
            (str(profile["id"]), jd_id),
        )
    row = execute(
        """
        insert into applications (student_profile_id, job_description_id, match_id, cover_note)
        values (%s, %s, %s, %s)
        returning id, status, applied_at
        """,
        (str(profile["id"]), jd_id, str(match["id"]) if match else None,
         body.get("cover_note")),
    )
    return {"application_id": str(row["id"]), "status": row["status"]}


@router.get("/applications")
def my_applications(user: AuthUser = Depends(require_perm("applications.create.own"))):
    profile = _profile_or_404(user)
    return fetch_all(
        """
        select a.id, a.status, a.applied_at, a.cover_note,
               jd.title, jd.kind, o.name as organization_name, jd.location,
               m.score
        from applications a
        join job_descriptions jd on jd.id = a.job_description_id
        join organizations o on o.id = jd.organization_id
        left join matches m on m.id = a.match_id
        where a.student_profile_id = %s
        order by a.applied_at desc
        """,
        (str(profile["id"]),),
    )


@router.get("/learning-resources")
def learning_resources(stream: str, code: str):
    try:
        cfg = stream_config(stream)
    except FileNotFoundError:
        raise HTTPException(404, "unknown stream")
    row = fetch_one("select id from skills where stream = %s and code = %s", (stream, code))
    if row is None:
        return []
    return fetch_all(
        "select title, provider, url, duration_hours, is_free from learning_resources "
        "where skill_id = %s order by duration_hours",
        (str(row["id"]),),
    )
