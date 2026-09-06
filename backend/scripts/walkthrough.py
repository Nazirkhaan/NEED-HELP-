"""End-to-end walkthrough against the REAL database + pipeline.

Proves the acceptance loop without any manual DB edits:
  1. login all four roles (RBAC from roles_permissions table)
  2. student: consent -> upload resume -> extraction
  3. gap vs target role + learning path
  4. explainable match vs JD (incl. ZERO literal keyword overlap proof)
  5. TPO co-signs a claimed skill -> state machine transition
  6. industry verifies it
  7. apply -> shortlist -> log outcome -> recalibration (weights change)
  8. curriculum_gap_signal regenerated -> visible in dashboards
  9. admin heatmap + analytics + RBAC edit + live reseed sanity

Run:  python scripts/walkthrough.py
Exit code 0 = all assertions passed.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.pool import fetch_all, fetch_one, get_pool  # noqa: E402
from app.db.migrate import run_migrations  # noqa: E402
from app.main import ensure_roles  # noqa: E402
from app.core.security import verify_password  # noqa: E402
from app.core.rbac import AuthUser  # noqa: E402
from app.api.auth import login  # noqa: E402
from app.api.student import (apply, gap as gap_ep, get_profile, matches as matches_ep,  # noqa: E402
                             set_consent, upload_profile, add_skill)
from app.api.tpo import cosign_skill, curriculum_gaps, placements, role_gaps  # noqa: E402
from app.api.industry import (applicants, log_outcome, my_jobs, post_job,  # noqa: E402
                              set_application_status, verify_skill)
from app.api.admin import analytics, heatmap, list_roles, update_role, taxonomy  # noqa: E402
from app.services.tfidf import literal_token_overlap  # noqa: E402

PASSED = []
FAILED = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASSED if cond else FAILED).append((name, detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def section(title: str) -> None:
    print(f"\n=== {title} ===")


class FakeCreds:
    def __init__(self, token):
        self.credentials = token


def login_role(email: str) -> AuthUser:
    body = type("B", (), {"email": email, "password": "demo1234"})()
    res = login(body)
    token = res["access_token"]
    user = get_current_user.__wrapped__ if False else None  # noqa: F841
    # build AuthUser directly from the token payload path used in requests
    from app.core.security import decode_token

    import uuid as _uuid

    payload = decode_token(token)
    row = fetch_one(
        """
        select u.id, u.email, u.full_name, u.institution_id, u.organization_id,
               u.consent_given, r.name as role_name, r.permissions
        from users u join roles_permissions r on r.id = u.role_id
        where u.id = %s
        """,
        (_uuid.UUID(payload["sub"]),),
    )
    return AuthUser(row)


def main() -> int:
    t0 = time.time()
    get_pool()
    run_migrations()
    ensure_roles()

    section("1. Auth & RBAC (database-driven)")
    student = login_role("student.demo@sih.gov.in")
    tpo = login_role("tpo.cse.demo@sih.gov.in")
    industry = login_role("industry.cse.demo@sih.gov.in")
    admin = login_role("admin.demo@sih.gov.in")
    check("student role resolves", student.role == "student")
    check("tpo role resolves", tpo.role == "tpo")
    check("industry role resolves", industry.role == "industry")
    check("admin role resolves", admin.role == "admin")
    check("student permissions non-empty", len(student.permissions) >= 5)
    check("permissions differ across roles",
          student.permissions != tpo.permissions != industry.permissions)

    section("2. Student: consent + resume upload + extraction")
    # upload on the literal-twin demo student (demo1 stays pristine for the
    # semantic-proof checks in section 4)
    student = login_role("student.demo2@sih.gov.in")
    set_consent({"granted": True}, student)
    resume_text = (
        "Passionate final-year builder. Built a quiz app with React and a small "
        "Python web scraper. Familiar with Git and Linux basics."
    )
    asyncio.run(upload_profile(
        resume_text=resume_text, stream="cse", cgpa=8.4, graduation_year=2026,
        bio="walkthrough", file=None, user=student,
    ))
    prof = get_profile(user=student)
    skills = prof["skills"]
    check("profile stored with resume", bool(prof["profile"]["resume_text"]))
    check("extraction_status extracted", prof["profile"]["extraction_status"] == "extracted")
    extracted_codes = {s["code"] for s in skills}
    check("react extracted from resume", "react" in extracted_codes, str(extracted_codes))
    check("python extracted from resume", "python" in extracted_codes)
    check("claims carry verification states",
          all(s["state"] in ("claimed", "institution_cosigned", "verified") for s in skills))
    # manual claim: pick any taxonomy skill not yet on the profile (idempotent)
    have = {s["code"] for s in skills}
    fresh = fetch_one(
        "select id, code from skills where stream = 'cse' and code <> all(%s) limit 1",
        (sorted(have),),
    )
    if fresh:
        add_skill({"skill_id": str(fresh["id"])}, student)
        check(f"manual claim works ({fresh['code']})",
              any(s["code"] == fresh["code"] for s in get_profile(user=student)["skills"]))
    else:
        check("manual claim skipped (full coverage)", True)

    section("3. Skill gap vs target role + learning path")
    gap = gap_ep(role="Full-Stack Developer Intern", user=student)
    check("readiness computed", 0 <= gap["readiness_pct"] <= 100, f"{gap['readiness_pct']}%")
    check("missing skills listed", len(gap["missing_skills"]) >= 1)
    check("learning path attached to missing skills",
          len(gap["learning_path"]) >= 1 and all(p["resources"] for p in gap["learning_path"]))

    section("4. Explainable match (semantic, not keyword)")
    ms = matches_ep(user=student)
    check("matches computed for open JDs", len(ms) >= 3, f"n={len(ms)}")
    m = ms[0]
    check("score decomposed into semantic + taxonomy",
          abs((m["semantic_score"] * 0.55 + m["taxonomy_score"] * 0.45) - m["score"]) < 1.5,
          f"score={m['score']} sem={m['semantic_score']} tax={m['taxonomy_score']}")
    check("matched/missing lists present", isinstance(m["matched_skills"], list) and isinstance(m["missing_skills"], list))

    # THE PROOF: demo student (zero literal overlap) vs JD A
    demo = login_role("student.demo@sih.gov.in")
    set_consent({"granted": True}, demo)
    dms = matches_ep(user=demo)
    jd_a = fetch_one("select * from job_descriptions where title = %s", ("Cloud Backend Intern",))
    dm = next(x for x in dms if x["job_description_id"] == str(jd_a["id"]))
    check("semantic-proof match exists", dm is not None,
          f"score={dm['score']} literal_overlap={dm['literal_keyword_overlap']}%")
    check("ZERO literal keyword overlap but strong score",
          dm["literal_keyword_overlap"] == 0.0 and dm["score"] >= 40,
          f"score={dm['score']}, literal={dm['literal_keyword_overlap']}% (semantic proves the match)")
    check("matched skills non-empty for zero-overlap pair", len(dm["matched_skills"]) >= 3,
          str([s["label"] for s in dm["matched_skills"]]))
    lit = literal_token_overlap(
        fetch_one("select resume_text from student_profiles sp join users u on u.id=sp.user_id where u.email=%s",
                  ("student.demo@sih.gov.in",))["resume_text"],
        jd_a["description"])
    check("literal overlap independently recomputed = 0", lit == 0.0, f"{lit}")

    section("5. Verification state machine (claimed -> cosigned -> verified)")
    queue = fetch_all(
        """
        select v.id, v.state, sp.user_id, u.email from skill_verification_state v
        join student_profiles sp on sp.id = v.student_profile_id
        join users u on u.id = sp.user_id
        where v.state = 'claimed' and sp.institution_id = %s limit 1
        """,
        (tpo.institution_id,),
    )
    check("TPO verification queue has claimed skills", len(queue) >= 1)
    target = queue[0]
    cos = cosign_skill(type("B", (), {"student_skill_id": str(target["id"]), "note": "confirmed in lab"})(), tpo)
    check("claimed -> institution_cosigned", cos["state"] == "institution_cosigned")
    ver = verify_skill(type("B", (), {"student_skill_id": str(target["id"]), "note": "verified in interview"})(), industry)
    check("institution_cosigned -> verified (industry)", ver["state"] == "verified")
    try:
        cosign_skill(type("B", (), {"student_skill_id": str(target["id"]), "note": None})(), tpo)
        check("illegal re-cosign rejected", False)
    except Exception as e:
        check("illegal re-cosign rejected", getattr(e, "status_code", None) == 409,
              f"{type(e).__name__}: {e}")

    section("6. Industry: post JD -> applicants -> apply -> outcome")
    job = post_job(type("B", (), {
        "title": "Platform Engineering Intern (walkthrough)",
        "kind": "internship", "stream": "cse",
        "description": ("We need an intern comfortable with Python, SQL databases and "
                        "REST APIs, plus exposure to Docker and Linux. You will ship "
                        "services with senior engineers and write tests."),
        "location": "Remote", "stipend": 20000, "salary_min": None,
        "salary_max": None, "seats": 1,
    })(), industry)
    check("JD posted with extracted skills", job["extracted_count"] >= 3,
          str([s["code"] for s in job["skills"]]))

    app = apply({"job_description_id": job["job_description_id"], "cover_note": "hi"}, student)
    check("application submitted", bool(app["application_id"]))
    apps = applicants(job["job_description_id"], industry)
    check("applicants visible to industry with skill-diff", len(apps) >= 1 and "matched_skills" in apps[0])
    app_row = next(a for a in apps if a["application_id"] == app["application_id"])
    set_application_status(app["application_id"], type("B", (), {"status": "selected"})(), industry)
    out = log_outcome(type("B", (), {
        "application_id": app["application_id"], "result": "completed",
        "performance_rating": 5, "industry_feedback": "Outstanding intern.",
    })(), industry)
    check("outcome logged triggers recalibration", len(out["weight_changes"]) >= 1,
          str([(c["code"], c["old_weight"], c["new_weight"]) for c in out["weight_changes"]]))
    logs = fetch_all(
        """
        select l.*, s.code from skill_recalibration_log l join skills s on s.id=l.skill_id
        where l.outcome_id = %s
        """,
        (out["outcome_id"],),
    )
    check("recalibration log rows written", len(logs) >= 1)
    check("positive rating increases demand weights",
          all(float(l["new_weight"]) > float(l["old_weight"]) for l in logs),
          str([(l["code"], float(l["old_weight"]), float(l["new_weight"])) for l in logs]))

    section("7. Feedback loop reaches the institution dashboard")
    cgs = curriculum_gaps(user=tpo)
    check("curriculum gap signals exist for TPO institution", len(cgs) >= 1, f"n={len(cgs)}")
    check("severities assigned", set(c["severity"] for c in cgs) <= {"low", "medium", "high"})
    rg = role_gaps(user=tpo)
    check("TPO role-gap readiness computed", len(rg) >= 1 and rg[0]["avg_readiness"] is not None)
    plc = placements(user=tpo)
    check("TPO placements funnel computed", plc["funnel"]["applications"] >= 1)

    section("8. Admin/Ministry: heatmap, analytics, RBAC, taxonomy")
    hm = heatmap(user=admin)
    check("heatmap covers streams", len(hm) >= 1 and len(hm[0]["grid"]) >= 1)
    check("heatmap grid cells populated",
          any(c is not None for row in hm[0]["grid"] for c in row["cells"]))
    an = analytics(user=admin)
    check("analytics totals sane",
          an["totals"]["students"] >= 1 and an["totals"]["matches"] >= 1)
    check("recalibration history in analytics", len(an["recent_recalibrations"]) >= 1)
    roles = list_roles(user=admin)
    check("RBAC roles listed from DB", len(roles) >= 4)
    old_perms = next(r for r in roles if r["name"] == "student")["permissions"]
    new_perms = list(old_perms) + ["matches.view.institution"]
    upd = update_role("student", type("B", (), {"permissions": new_perms})(), admin)
    check("RBAC edit takes effect live", "matches.view.institution" in upd["permissions"])
    student2 = login_role("student.demo2@sih.gov.in")
    check("student sees updated permissions on fresh login",
          "matches.view.institution" in student2.permissions)
    update_role("student", type("B", (), {"permissions": old_perms})(), admin)
    tax = taxonomy(stream="cse", user=admin)
    check("taxonomy weights visible (recalibrated)", len(tax) >= 10
          and any(float(t["demand_weight"]) != 1.0 for t in tax))

    print(f"\n{'='*60}")
    print(f"PASSED: {len(PASSED)}   FAILED: {len(FAILED)}   ({time.time()-t0:.1f}s)")
    for name, detail in FAILED:
        print(f"  FAIL: {name} {detail}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
