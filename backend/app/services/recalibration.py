"""Outcome-feedback loop (the closed loop that makes this an MVP, not a CRUD app).

Mechanism (one, fully implemented and demoable):

1. When industry logs an outcome (performance rating 1-5) for a completed
   internship/placement, every skill demanded by that JD is reweighted:
       hired + rating>=4      -> demand_weight +5%
       hired + rating==3      -> demand_weight +2%
       completed + rating>=4  -> demand_weight +4%
       completed + rating==3  -> no change
       rating<=2 or dropped   -> demand_weight -7%
   Weights are clamped to [0.5, 2.5]; every change is written to
   skill_recalibration_log with old/new weight and a human-readable reason.
   demand_weight feeds the matching engine's taxonomy score, so future match
   scores immediately reflect what industry actually valued.

2. The same trigger regenerates curriculum_gap_signal rows for the student's
   institution: per-skill gap counts (students missing a demanded skill) with
   severity, which the Institution and Ministry dashboards render as alerts.

Called from the async outcome-logging API and from the seeder.
"""
from app.db.pool import aexecute, afetch_all, afetch_one, atransaction

MIN_W, MAX_W = 0.5, 2.5


def _delta_for(result: str, rating: int | None) -> int:
    if result == "hired":
        return 5 if (rating or 0) >= 4 else 2
    if result == "dropped":
        return -7
    # completed
    if rating is None:
        return 0
    if rating >= 4:
        return 4
    if rating <= 2:
        return -7
    return 0


def _reason_for(result: str, rating: int | None, delta: int) -> str:
    if delta > 0:
        return f"industry valued: {result} with rating {rating or '-'}/5 -> +{delta}% demand"
    if delta < 0:
        return f"industry undervalued: {result} with rating {rating or '-'}/5 -> {delta}% demand"
    return f"neutral outcome: {result} with rating {rating}/5 -> no change"


async def apply_outcome_recalibration(outcome_id: str) -> dict:
    outcome = await afetch_one("select * from outcomes where id = %s", (outcome_id,))
    if outcome is None:
        raise ValueError("outcome not found")
    jd = await afetch_one(
        "select * from job_descriptions where id = %s", (outcome["job_description_id"],)
    )
    profile = await afetch_one(
        "select * from student_profiles where id = %s", (outcome["student_profile_id"],)
    )
    rating = outcome["performance_rating"]
    result = outcome["result"]
    delta = _delta_for(result, rating)

    changes = []
    for entry in (jd["extracted_skills"] or []):
        sid = str(entry["skill_id"])
        skill = await afetch_one("select * from skills where id = %s", (sid,))
        if skill is None:
            continue
        old = float(skill["demand_weight"])
        new = round(min(MAX_W, max(MIN_W, old * (1 + delta / 100.0))), 4)
        if new != old:
            async with atransaction() as cur:
                await cur.execute(
                    "update skills set demand_weight = %s where id = %s", (new, sid)
                )
                await cur.execute(
                    """
                    insert into skill_recalibration_log
                        (outcome_id, skill_id, old_weight, new_weight, reason)
                    values (%s, %s, %s, %s, %s)
                    """,
                    (outcome_id, sid, old, new,
                     _reason_for(result, rating, delta)),
                )
            changes.append({
                "skill_id": sid, "code": skill["code"], "label": skill["label"],
                "old_weight": old, "new_weight": new,
            })

    signals = []
    if profile["institution_id"]:
        signals = await rebuild_curriculum_signals(str(profile["institution_id"]))

    return {"outcome_id": outcome_id, "weight_changes": changes,
            "curriculum_signals_regenerated": len(signals)}


async def rebuild_curriculum_signals(institution_id: str) -> list[dict]:
    """Recompute curriculum_gap_signal rows for one institution (its stream).

    For every skill demanded by open JDs in the stream: how many of the
    institution's students lack it (gap_count), aggregate JD demand, severity.
    """
    inst = await afetch_one("select * from institutions where id = %s", (institution_id,))
    if inst is None:
        return []
    stream = inst["stream"]

    students = await afetch_all(
        """
        select sp.id, coalesce(jsonb_agg(distinct s.id) filter (where s.id is not null), '[]') as skill_ids
        from student_profiles sp
        left join skill_verification_state v on v.student_profile_id = sp.id
        left join skills s on s.id = v.skill_id
        where sp.institution_id = %s
        group by sp.id
        """,
        (institution_id,),
    )
    jds = await afetch_all(
        "select extracted_skills from job_descriptions where stream = %s and status = 'open'",
        (stream,),
    )

    # aggregate demand + per-skill student-missing counts
    demand: dict[str, float] = {}
    jd_count: dict[str, int] = {}
    for jd in jds:
        for e in (jd["extracted_skills"] or []):
            sid = str(e["skill_id"])
            demand[sid] = demand.get(sid, 0.0) + float(e.get("weight", 1.0))
            jd_count[sid] = jd_count.get(sid, 0) + 1

    skill_ids = list(demand.keys())
    skill_rows = await afetch_all(
        "select id, demand_weight, label from skills where id = any(%s)",
        (skill_ids,),
    ) if skill_ids else []
    weights = {str(r["id"]): float(r["demand_weight"]) for r in skill_rows}
    labels = {str(r["id"]): r["label"] for r in skill_rows}

    missing_counts: dict[str, int] = {sid: 0 for sid in skill_ids}
    student_count = len(students)
    if student_count:
        for st in students:
            have = {str(x) for x in st["skill_ids"]}
            for sid in skill_ids:
                if sid not in have:
                    missing_counts[sid] += 1

    rows = []
    async with atransaction() as cur:
        await cur.execute(
            "delete from curriculum_gap_signal where institution_id = %s",
            (institution_id,),
        )
        for sid in skill_ids:
            gap_count = missing_counts[sid]
            demand_score = round(demand[sid] * weights.get(sid, 1.0), 3)
            ratio = gap_count / student_count if student_count else 0.0
            if ratio >= 0.6 and demand_score >= 1.5:
                severity = "high"
            elif ratio >= 0.35 and demand_score >= 0.8:
                severity = "medium"
            else:
                severity = "low"
            detail = {
                "missing_ratio": round(ratio, 3),
                "demanded_by_jds": jd_count[sid],
                "skill_label": labels.get(sid),
                "demand_weight": weights.get(sid, 1.0),
            }
            await cur.execute(
                """
                insert into curriculum_gap_signal
                    (institution_id, stream, skill_id, gap_count, student_count,
                     demand_score, severity, detail)
                values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                returning id, skill_id, gap_count, demand_score, severity, detail
                """,
                (institution_id, stream, sid, gap_count, student_count,
                 demand_score, severity, _json(detail)),
            )
            rows.append(await cur.fetchone())
    return rows


def _json(obj) -> str:
    import json
    return json.dumps(obj)
