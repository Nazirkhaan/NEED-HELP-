"""Skill-gap computation against target roles + learning-path recommendation.

Role requirements come from the stream config (backend/configs/stream_*.json),
never hardcoded. Learning resources are taxonomy-linked rows.
"""
from app.db.pool import afetch_all, afetch_one
from app.services.config_loader import stream_config

STATE_FACTOR = {"verified": 1.0, "institution_cosigned": 0.9, "claimed": 0.7}


def list_target_roles(stream: str) -> list[dict]:
    cfg = stream_config(stream)
    return [{"name": r["name"], "n_required": len(r["required"])} for r in cfg["target_roles"]]


async def compute_role_gap(student_profile_id: str, role_name: str) -> dict:
    profile = await afetch_one(
        "select * from student_profiles where id = %s", (student_profile_id,)
    )
    if profile is None:
        raise ValueError("student profile not found")
    stream = profile["stream"]
    cfg = stream_config(stream)
    role = next((r for r in cfg["target_roles"] if r["name"] == role_name), None)
    if role is None:
        raise ValueError(f"unknown target role '{role_name}' for stream '{stream}'")

    student_skills = {
        str(r["id"]): r
        for r in await afetch_all(
            """
            select s.id, s.code, s.label, s.category, v.state
            from skill_verification_state v join skills s on s.id = v.skill_id
            where v.student_profile_id = %s
            """,
            (student_profile_id,),
        )
    }

    matched, missing = [], []
    num = den = 0.0
    for req in role["required"]:
        row = await afetch_one("select id from skills where stream=%s and code=%s",
                               (stream, req["code"]))
        sid = str(row["id"])
        w = float(req["weight"])
        den += w
        if sid in student_skills:
            factor = STATE_FACTOR.get(student_skills[sid]["state"], 0.7)
            num += w * factor
            matched.append({
                "skill_id": sid, "code": req["code"],
                "label": student_skills[sid]["label"],
                "weight": w, "student_state": student_skills[sid]["state"],
                "credit": round(factor, 2),
            })
        else:
            label_row = await afetch_one("select label from skills where id=%s", (sid,))
            missing.append({
                "skill_id": sid, "code": req["code"],
                "label": label_row["label"], "weight": w,
            })

    missing.sort(key=lambda m: -m["weight"])
    matched.sort(key=lambda m: -m["weight"])
    readiness = round(100 * num / den, 1) if den else 0.0

    # Learning path: top missing skills first, with resources
    path = []
    for m in missing[:6]:
        resources = await afetch_all(
            "select title, provider, url, duration_hours, is_free "
            "from learning_resources where skill_id = %s order by duration_hours",
            (m["skill_id"],),
        )
        path.append({
            "skill_id": m["skill_id"], "code": m["code"], "label": m["label"],
            "priority_weight": m["weight"], "resources": resources,
            "est_hours": sum(float(r["duration_hours"] or 0) for r in resources),
        })

    return {
        "role": role_name,
        "stream": stream,
        "readiness_pct": readiness,
        "matched_skills": matched,
        "missing_skills": missing,
        "learning_path": path,
        "total_learning_hours": round(sum(p["est_hours"] for p in path), 1),
    }
