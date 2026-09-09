"""Admin / Ministry endpoints: cross-institution heatmap, curriculum-gap
alerts, placement analytics, dynamic RBAC editing, taxonomy inspection,
and live re-seeding of a different stream without code changes."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.rbac import AuthUser, require_perm
from app.db.pool import aexecute, afetch_all, afetch_one, atransaction
from app.services.config_loader import reload_configs, stream_config
from app.services.gap import STATE_FACTOR
from app.services.recalibration import rebuild_curriculum_signals

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/heatmap")
async def heatmap(stream: str | None = None,
                  user: AuthUser = Depends(require_perm("dashboard.view.all"))):
    """Skill-gap heatmap: institutions × target roles, cell = avg readiness %,
    plus per-role missing-skill percentages across the stream."""
    streams = [stream] if stream else [
        r["stream"] for r in await afetch_all("select distinct stream from institutions")
    ]
    result = []
    for st in streams:
        try:
            cfg = stream_config(st)
        except FileNotFoundError:
            continue
        insts = await afetch_all(
            "select id, name from institutions where stream = %s order by name", (st,)
        )
        skill_rows = await afetch_all(
            "select id, code, label, demand_weight from skills where stream = %s", (st,)
        )
        code_to_id = {r["code"]: str(r["id"]) for r in skill_rows}
        weight_by_id = {str(r["id"]): float(r["demand_weight"]) for r in skill_rows}
        label_by_code = {r["code"]: r["label"] for r in skill_rows}
        students = await afetch_all(
            """
            select sp.id, sp.institution_id,
                   coalesce(jsonb_agg(distinct s.id) filter (where s.id is not null), '[]') as skill_ids,
                   coalesce(jsonb_object_agg(v.skill_id::text, v.state)
                            filter (where v.skill_id is not null), '{}') as state_by_skill
            from student_profiles sp
            left join skill_verification_state v on v.student_profile_id = sp.id
            left join skills s on s.id = v.skill_id
            where sp.stream = %s
            group by sp.id, sp.institution_id
            """,
            (st,),
        )
        roles_out = []
        for role in cfg["target_roles"]:
            reqs = [(code_to_id[r["code"]], float(r["weight"])) for r in role["required"]
                    if r["code"] in code_to_id]
            if not reqs:
                continue
            per_inst = {}
            missing_counts = {sid: 0 for sid, _ in reqs}
            n = 0
            for stud in students:
                have = {str(x) for x in stud["skill_ids"]}
                state_by_skill = stud["state_by_skill"] or {}
                num = den = 0.0
                for sid, w in reqs:
                    den += w * weight_by_id.get(sid, 1.0)
                    if sid in have:
                        num += w * weight_by_id.get(sid, 1.0) * STATE_FACTOR.get(
                            state_by_skill.get(sid, "claimed"), 0.7)
                    else:
                        missing_counts[sid] += 1
                readiness = 100 * num / den if den else 0.0
                n += 1
                iid = str(stud["institution_id"]) if stud["institution_id"] else "none"
                per_inst.setdefault(iid, []).append(readiness)
            id_to_code = {sid: next((code for code, sid2 in code_to_id.items() if sid2 == sid), sid)
                          for sid in missing_counts}
            roles_out.append({
                "role": role["name"],
                "n_students": n,
                "avg_readiness": round(sum(
                    v for vals in per_inst.values() for v in vals) / n, 1) if n else None,
                "missing_skills": [
                    {"code": id_to_code[sid], "label": label_by_code.get(id_to_code[sid], id_to_code[sid]),
                     "pct_missing": round(100 * c / n, 1)}
                    for sid, c in sorted(missing_counts.items(), key=lambda kv: -kv[1])[:6]
                ],
            })
        cells = {}
        for inst in insts:
            for role in roles_out:
                cells[f"{inst['id']}::{role['role']}"] = None  # filled below
        # build grid: inst × role avg readiness
        grid = []
        for inst in insts:
            row_cells = []
            for role in cfg["target_roles"]:
                reqs = [(code_to_id[r["code"]], float(r["weight"])) for r in role["required"]
                        if r["code"] in code_to_id]
                vals = []
                for stud in students:
                    if str(stud["institution_id"]) != str(inst["id"]):
                        continue
                    have = {str(x) for x in stud["skill_ids"]}
                    state_by_skill = stud["state_by_skill"] or {}
                    num = den = 0.0
                    for sid, w in reqs:
                        den += w * weight_by_id.get(sid, 1.0)
                        if sid in have:
                            num += w * weight_by_id.get(sid, 1.0) * STATE_FACTOR.get(
                                state_by_skill.get(sid, "claimed"), 0.7)
                    if den:
                        vals.append(100 * num / den)
                row_cells.append(round(sum(vals) / len(vals), 1) if vals else None)
            grid.append({"institution": inst["name"], "institution_id": str(inst["id"]),
                         "cells": row_cells})
        result.append({
            "stream": st,
            "stream_name": cfg["name"],
            "roles": [r["name"] for r in cfg["target_roles"]],
            "grid": grid,
            "role_details": roles_out,
        })
    return result


@router.get("/curriculum-gaps")
async def all_curriculum_gaps(severity: str | None = None,
                              user: AuthUser = Depends(require_perm("curriculum.view.all"))):
    sql = """
        select c.*, s.code, s.label, s.category, i.name as institution_name, i.stream
        from curriculum_gap_signal c
        join skills s on s.id = c.skill_id
        join institutions i on i.id = c.institution_id
    """
    rows = await afetch_all(sql + " order by case c.severity when 'high' then 0 when 'medium' then 1 else 2 end, c.demand_score desc")
    if severity:
        rows = [r for r in rows if r["severity"] == severity]
    return rows


@router.get("/analytics")
async def analytics(user: AuthUser = Depends(require_perm("analytics.view.all"))):
    totals = await afetch_one(
        """
        select
            (select count(*) from student_profiles) as students,
            (select count(*) from institutions) as institutions,
            (select count(*) from organizations) as organizations,
            (select count(*) from job_descriptions) as jobs,
            (select count(*) from applications) as applications,
            (select count(*) from matches) as matches,
            (select count(*) from outcomes) as outcomes,
            (select count(*) from skill_verification_state where state = 'claimed') as claimed_skills,
            (select count(*) from skill_verification_state where state = 'institution_cosigned') as cosigned_skills,
            (select count(*) from skill_verification_state where state = 'verified') as verified_skills
        """
    )
    funnel = await afetch_one(
        """
        select count(*) as applied,
               count(*) filter (where status in ('shortlisted','selected')) as shortlisted,
               count(*) filter (where status = 'selected') as selected,
               (select count(*) from outcomes o where o.result = 'completed') as completed,
               (select count(*) from outcomes o where o.result = 'hired') as hired
        from applications
        """
    )
    avg_rating = await afetch_one(
        "select round(avg(performance_rating), 2) as avg_rating, count(*) as n from outcomes"
    )
    top_demand = await afetch_all(
        """
        select s.code, s.label, s.demand_weight,
               sum((e->>'weight')::numeric) as total_jd_weight,
               count(jd.id) as n_jds
        from job_descriptions jd
        cross join lateral jsonb_array_elements(jd.extracted_skills) e
        join skills s on s.id = (e->>'skill_id')::uuid
        group by s.id, s.code, s.label, s.demand_weight
        order by total_jd_weight desc
        limit 12
        """
    )
    recal = await afetch_all(
        """
        select l.*, s.code, s.label, o.result, o.performance_rating
        from skill_recalibration_log l
        join skills s on s.id = l.skill_id
        join outcomes o on o.id = l.outcome_id
        order by l.created_at desc
        limit 15
        """
    )
    stream_split = await afetch_all(
        """
        select stream,
               count(*) as students,
               (select count(*) from applications a
                 join student_profiles sp2 on sp2.id = a.student_profile_id
                 where sp2.stream = sp.stream) as applications,
               (select count(*) from outcomes o
                 join student_profiles sp3 on sp3.id = o.student_profile_id
                 where sp3.stream = sp.stream) as outcomes
        from student_profiles sp
        group by stream
        """
    )
    alerts = await afetch_all(
        """
        select c.severity, count(*) as n from curriculum_gap_signal c
        group by c.severity
        """
    )
    return {
        "totals": totals,
        "funnel": funnel,
        "avg_outcome_rating": avg_rating,
        "top_demand_skills": top_demand,
        "recent_recalibrations": recal,
        "stream_split": stream_split,
        "gap_alert_counts": alerts,
    }


# ---------------- RBAC ----------------

@router.get("/roles")
async def list_roles(user: AuthUser = Depends(require_perm("rbac.manage"))):
    return await afetch_all(
        "select id, name, display_name, permissions, description, updated_at "
        "from roles_permissions order by name"
    )


class RoleUpdateBody(BaseModel):
    permissions: list[str]


@router.put("/roles/{role_name}")
async def update_role(role_name: str, body: RoleUpdateBody,
                      user: AuthUser = Depends(require_perm("rbac.manage"))):
    role = await afetch_one("select * from roles_permissions where name = %s", (role_name,))
    if role is None:
        raise HTTPException(404, "role not found")
    perms = sorted(set(p.strip() for p in body.permissions if p.strip()))
    async with atransaction() as cur:
        await cur.execute(
            """
            insert into rbac_audit_log (changed_by, role_id, old_permissions, new_permissions)
            values (%s, %s, %s::jsonb, %s::jsonb)
            """,
            (user.id, role["id"], _json(role["permissions"]), _json(perms)),
        )
        await cur.execute(
            "update roles_permissions set permissions = %s::jsonb, updated_at = now() where id = %s",
            (_json(perms), role["id"]),
        )
    return {"role": role_name, "permissions": perms,
            "note": "Effective immediately — permissions are read from the DB on every request."}


@router.get("/rbac-audit")
async def rbac_audit(user: AuthUser = Depends(require_perm("rbac.manage"))):
    return await afetch_all(
        """
        select a.*, r.name as role_name, u.email as changed_by_email
        from rbac_audit_log a
        join roles_permissions r on r.id = a.role_id
        left join users u on u.id = a.changed_by
        order by a.created_at desc limit 20
        """
    )


# ---------------- Taxonomy ----------------

@router.get("/skills")
async def taxonomy(stream: str, user: AuthUser = Depends(require_perm("taxonomy.manage"))):
    rows = await afetch_all(
        """
        select s.id, s.code, s.label, s.category, s.demand_weight, s.embedding_provider,
               (select count(*) from skill_recalibration_log l where l.skill_id = s.id) as recalibrations,
               (select max(l.created_at) from skill_recalibration_log l where l.skill_id = s.id) as last_recalibrated
        from skills s where s.stream = %s order by s.demand_weight desc
        """,
        (stream,),
    )
    for r in rows:
        r["id"] = str(r["id"])
        r["demand_weight"] = float(r["demand_weight"])
    return rows


class WeightBody(BaseModel):
    demand_weight: float


@router.put("/skills/{skill_id}/weight")
async def set_weight(skill_id: str, body: WeightBody,
                     user: AuthUser = Depends(require_perm("taxonomy.manage"))):
    if not 0.3 <= body.demand_weight <= 3.0:
        raise HTTPException(400, "demand_weight must be within [0.3, 3.0]")
    row = await aexecute(
        "update skills set demand_weight = %s where id = %s returning id, code, demand_weight",
        (body.demand_weight, skill_id),
    )
    if row is None:
        raise HTTPException(404, "skill not found")
    return {"skill_id": str(row["id"]), "code": row["code"],
            "demand_weight": float(row["demand_weight"])}


# ---------------- Reseed ----------------

class ReseedBody(BaseModel):
    stream: str
    students_per_institution: int = 16
    note: str | None = None


@router.post("/reseed")
async def reseed(body: ReseedBody, user: AuthUser = Depends(require_perm("reseed.run"))):
    try:
        stream_config(body.stream)
    except FileNotFoundError:
        raise HTTPException(404, f"No config for stream '{body.stream}' — add backend/configs/stream_{body.stream}.json")
    from seed.generate import generate_stream

    reload_configs()
    summary = await generate_stream(
        body.stream,
        wipe=True,
        students_per_institution=body.students_per_institution,
        note=body.note or f"Live reseed via admin API by {user.email}",
    )
    reload_configs()
    return summary


@router.get("/institutions")
async def institutions(user: AuthUser = Depends(require_perm("dashboard.view.all"))):
    return await afetch_all(
        """
        select i.*, count(sp.id) as students
        from institutions i
        left join student_profiles sp on sp.institution_id = i.id
        group by i.id order by i.stream, i.name
        """
    )


def _json(obj) -> str:
    import json
    return json.dumps(obj)
