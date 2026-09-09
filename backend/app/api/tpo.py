"""Institution / TPO endpoints: verification queue + co-sign, student roster,
curriculum-gap signals, placement analytics."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.rbac import AuthUser, require_perm
from app.db.pool import afetch_all, afetch_one
from app.services import matching
from app.services.config_loader import stream_config
from app.services.gap import STATE_FACTOR
from app.services.recalibration import rebuild_curriculum_signals
from app.services.verification import cosign

router = APIRouter(prefix="/api/tpo", tags=["tpo"])


class CosignBody(BaseModel):
    student_skill_id: str
    note: str | None = None


def _own_institution(user: AuthUser) -> str:
    if not user.institution_id:
        raise HTTPException(400, "TPO account has no institution linked")
    return user.institution_id


@router.get("/students")
async def students(user: AuthUser = Depends(require_perm("students.view.institution"))):
    inst = _own_institution(user)
    return await afetch_all(
        """
        select sp.id, u.full_name, u.email, sp.stream, sp.cgpa, sp.graduation_year,
               sp.extraction_status,
               count(v.id) filter (where v.state = 'claimed') as claimed_count,
               count(v.id) filter (where v.state = 'institution_cosigned') as cosigned_count,
               count(v.id) filter (where v.state = 'verified') as verified_count,
               count(v.id) as total_skills
        from student_profiles sp
        join users u on u.id = sp.user_id
        left join skill_verification_state v on v.student_profile_id = sp.id
        where sp.institution_id = %s
        group by sp.id, u.full_name, u.email, sp.stream, sp.cgpa,
                 sp.graduation_year, sp.extraction_status
        order by u.full_name
        """,
        (inst,),
    )


@router.get("/students/{student_profile_id}")
async def student_detail(student_profile_id: str,
                         user: AuthUser = Depends(require_perm("students.view.institution"))):
    inst = _own_institution(user)
    profile = await afetch_one(
        """
        select sp.*, u.full_name, u.email from student_profiles sp
        join users u on u.id = sp.user_id
        where sp.id = %s and sp.institution_id = %s
        """,
        (student_profile_id, inst),
    )
    if profile is None:
        raise HTTPException(404, "Student not in your institution")
    skills = await afetch_all(
        """
        select v.id, v.state, s.code, s.label, s.category
        from skill_verification_state v join skills s on s.id = v.skill_id
        where v.student_profile_id = %s order by s.category, s.label
        """,
        (student_profile_id,),
    )
    return {"student": {k: v for k, v in profile.items() if k != "embedding"}, "skills": skills}


@router.get("/verification-queue")
async def verification_queue(user: AuthUser = Depends(require_perm("skills.cosign.institution"))):
    inst = _own_institution(user)
    return await afetch_all(
        """
        select v.id, v.state, v.claimed_at, v.extracted_from_resume,
               s.code, s.label, s.category,
               sp.id as student_profile_id, u.full_name
        from skill_verification_state v
        join skills s on s.id = v.skill_id
        join student_profiles sp on sp.id = v.student_profile_id
        join users u on u.id = sp.user_id
        where sp.institution_id = %s and v.state = 'claimed'
        order by v.claimed_at
        """,
        (inst,),
    )


@router.post("/cosign")
async def cosign_skill(body: CosignBody, user: AuthUser = Depends(require_perm("skills.cosign.institution"))):
    row = await cosign(body.student_skill_id, {"id": user.id, "institution_id": user.institution_id}, body.note)
    await matching.compute_matches_for_student(str(row["student_profile_id"]))
    return {
        "student_skill_id": str(row["id"]),
        "state": row["state"],
        "note": "Co-signed. Industry can now verify it; matches recomputed.",
    }


@router.get("/curriculum-gaps")
async def curriculum_gaps(user: AuthUser = Depends(require_perm("curriculum.view.institution"))):
    inst = _own_institution(user)
    rows = await afetch_all(
        """
        select c.*, s.code, s.label, s.category
        from curriculum_gap_signal c join skills s on s.id = c.skill_id
        where c.institution_id = %s
        order by case c.severity when 'high' then 0 when 'medium' then 1 else 2 end,
                 c.demand_score desc
        """,
        (inst,),
    )
    return rows


@router.post("/curriculum-gaps/refresh")
async def refresh_curriculum_gaps(user: AuthUser = Depends(require_perm("curriculum.view.institution"))):
    inst = _own_institution(user)
    rows = await rebuild_curriculum_signals(inst)
    return {"regenerated": len(rows)}


@router.get("/placements")
async def placements(user: AuthUser = Depends(require_perm("placements.view.institution"))):
    inst = _own_institution(user)
    rows = await afetch_all(
        """
        select a.id as application_id, a.status, a.applied_at,
               u.full_name, jd.title, jd.kind, o.name as organization_name,
               m.score, out2.result, out2.performance_rating, out2.industry_feedback
        from applications a
        join student_profiles sp on sp.id = a.student_profile_id
        join users u on u.id = sp.user_id
        join job_descriptions jd on jd.id = a.job_description_id
        join organizations o on o.id = jd.organization_id
        left join matches m on m.id = a.match_id
        left join outcomes out2 on out2.application_id = a.id
        where sp.institution_id = %s
        order by a.applied_at desc
        """,
        (inst,),
    )
    funnel = await afetch_one(
        """
        select count(*) as applications,
               count(*) filter (where a.status in ('shortlisted','selected')) as shortlisted,
               count(*) filter (where a.status = 'selected') as selected,
               count(out2.id) filter (where out2.result = 'completed') as completed,
               count(out2.id) filter (where out2.result = 'hired') as hired
        from applications a
        join student_profiles sp on sp.id = a.student_profile_id
        left join outcomes out2 on out2.application_id = a.id
        where sp.institution_id = %s
        """,
        (inst,),
    )
    return {"applications": rows, "funnel": funnel}


@router.get("/role-gaps")
async def role_gaps(user: AuthUser = Depends(require_perm("gaps.view.institution"))):
    """Per-target-role readiness of this institution's students (heatmap-lite)."""
    inst = _own_institution(user)
    inst_row = await afetch_one("select stream from institutions where id = %s", (inst,))
    stream = inst_row["stream"]
    cfg = stream_config(stream)
    students = await afetch_all(
        """
        select sp.id, coalesce(jsonb_agg(distinct s.id) filter (where s.id is not null), '[]') as skill_ids,
               coalesce(jsonb_object_agg(v.skill_id::text, v.state) filter (where v.skill_id is not null), '{}') as state_by_skill
        from student_profiles sp
        left join skill_verification_state v on v.student_profile_id = sp.id
        left join skills s on s.id = v.skill_id
        where sp.institution_id = %s
        group by sp.id
        """,
        (inst,),
    )
    skill_rows = await afetch_all(
        "select id, code, demand_weight from skills where stream = %s", (stream,)
    )
    code_to_id = {r["code"]: str(r["id"]) for r in skill_rows}
    weight_by_id = {str(r["id"]): float(r["demand_weight"]) for r in skill_rows}

    out = []
    for role in cfg["target_roles"]:
        reqs = [(code_to_id[r["code"]], float(r["weight"])) for r in role["required"]
                if r["code"] in code_to_id]
        if not reqs or not students:
            out.append({"role": role["name"], "avg_readiness": None, "n_students": 0})
            continue
        readiness_vals = []
        missing_counts = {sid: 0 for sid, _ in reqs}
        for st in students:
            have = {str(x) for x in st["skill_ids"]}
            state_by_skill = st["state_by_skill"] or {}
            num = den = 0.0
            for sid, w in reqs:
                den += w * weight_by_id.get(sid, 1.0)
                if sid in have:
                    num += w * weight_by_id.get(sid, 1.0) * STATE_FACTOR.get(state_by_skill.get(sid, "claimed"), 0.7)
                else:
                    missing_counts[sid] += 1
            readiness_vals.append(100 * num / den if den else 0)
        out.append({
            "role": role["name"],
            "n_students": len(students),
            "avg_readiness": round(sum(readiness_vals) / len(readiness_vals), 1),
            "missing_skill_pcts": [
                {"code": sid, "pct_missing": round(100 * missing_counts[sid] / len(students), 1)}
                for sid, _ in reqs
            ],
        })
    return out
