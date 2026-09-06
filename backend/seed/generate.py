"""Deterministic synthetic data generator for SIH26044.

Everything generated here is labelled `is_synthetic = true` in the database and
rendered with a "Synthetic demo data" tag in the UI. Determinism: a fixed RNG
seed per stream, so demo walkthroughs are reproducible.

The generator is config-driven (backend/configs/stream_<key>.json) — re-seeding
for a different stream (e.g. ECE) is a config + API action, not a code change.
"""
import json
import random
from datetime import datetime, timedelta, timezone

from app.core.security import hash_password
from app.db.pool import execute, fetch_all, fetch_one, transaction
from app.services import embeddings
from app.services.config_loader import stream_config
from app.services.profile_pipeline import process_job_description, process_student_profile
from app.services.recalibration import apply_outcome_recalibration, rebuild_curriculum_signals

DEMO_PASSWORD = "demo1234"
ADMIN_EMAIL = "admin.demo@sih.gov.in"
FIRST_NAMES = [
    "Aarav", "Ananya", "Rohit", "Priya", "Vikram", "Sneha", "Arjun", "Kavya",
    "Karthik", "Meera", "Rahul", "Divya", "Siddharth", "Pooja", "Aditya",
    "Ishita", "Nikhil", "Shreya", "Varun", "Nandini", "Harsh", "Tanvi",
    "Yash", "Riya", "Devansh", "Aishwarya", "Manav", "Sanya", "Parth", "Neha",
    "Aryan", "Kritika", "Sanjay", "Deepika", "Gaurav", "Anjali", "Naveen",
    "Swara", "Tarun", "Bhavna",
]
LAST_NAMES = [
    "Sharma", "Iyer", "Patel", "Reddy", "Gupta", "Nair", "Verma", "Joshi",
    "Menon", "Rao", "Kulkarni", "Chatterjee", "Pillai", "Desai", "Bhatt",
    "Mehta", "Singh", "Kapoor", "Agarwal", "Murthy",
]

INSTITUTIONS = {
    "cse": [
        {"name": "Sunrise Institute of Technology", "city": "Pune"},
        {"name": "Greenfield Engineering College", "city": "Nagpur"},
    ],
    "ece": [
        {"name": "Meridian Institute of Engineering", "city": "Chennai"},
        {"name": "Silver Oak Polytechnic", "city": "Coimbatore"},
    ],
}

# ---- The semantic-proof demo pair (CSE) ------------------------------------
# Student A's resume shares ZERO literal content tokens with JD A's text, yet
# the taxonomy (aliases) + embeddings produce a strong, explainable match.
DEMO_SEMANTIC = {
    "email": "student.demo@sih.gov.in",
    "first": "Ananya", "last": "Iyer",
    "resume": (
        "Final-year CSE undergraduate. Created the registration portal for our "
        "college fest: designed normalized table structures in PostgreSQL and "
        "tuned structured query language reports for the organising committee. "
        "Ran event-driven functions on Amazon's cloud for ticket validation and "
        "packed each release as portable container images with automated CI. "
        "Wrangled sales records using dataframes to produce nightly summaries."
    ),
    "skills": {
        "sql": "verified",
        "pandas": "verified",
        "aws": "institution_cosigned",
        "rest_api": "institution_cosigned",
        "python": "claimed",
        "docker": "claimed",
    },
    "cgpa": 8.7,
}
# Student B: the literal twin — same target skills, spelled with the exact
# canonical keywords, so the raw keyword overlap is high.
DEMO_LITERAL = {
    "email": "student.demo2@sih.gov.in",
    "first": "Rohit", "last": "Verma",
    "resume": (
        "Backend-focused final-year student. Wrote SQL queries and REST APIs in "
        "Python for a commerce site, deployed Docker containers on AWS, and "
        "analysed sales data with Pandas. Comfortable with Git and pytest unit "
        "testing."
    ),
    "skills": {
        "sql": "verified",
        "rest_api": "verified",
        "python": "institution_cosigned",
        "aws": "claimed",
        "docker": "claimed",
        "pandas": "institution_cosigned",
        "git": "claimed",
    },
    "cgpa": 8.1,
}
JD_A = {
    "org": "CloudNest",
    "title": "Cloud Backend Intern",
    "kind": "internship",
    "description": (
        "Own core backend features of our multi-tenant SaaS platform. Day to "
        "day: shape relational schemas, write efficient SQL, build and document "
        "REST APIs, deploy Docker-based workloads on AWS, and analyse product "
        "usage with Pandas. You will join a squad of five engineers shipping "
        "weekly to production."
    ),
    "location": "Bengaluru (Hybrid)",
    "stipend": 25000,
    "seats": 3,
}

STATE_TIMESTAMP_BASE = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)


def _rnd_for(stream: str, seed: int) -> random.Random:
    return random.Random(f"sih26044:{stream}:{seed}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _upsert_taxonomy(stream: str, cfg: dict) -> int:
    with transaction() as cur:
        for s in cfg["skills"]:
            cur.execute(
                """
                insert into skills (stream, code, label, category, aliases, demand_weight)
                values (%s, %s, %s, %s, %s, %s)
                on conflict (stream, code) do update set
                    label = excluded.label,
                    category = excluded.category,
                    aliases = excluded.aliases,
                    demand_weight = excluded.demand_weight,
                    active = true
                """,
                (stream, s["code"], s["label"], s["category"],
                 list(s.get("aliases", [])), s.get("demand_weight", 1.0)),
            )
    count = len(cfg["skills"])
    # learning resources (per skill, from config)
    with transaction() as cur:
        cur.execute("delete from learning_resources where stream = %s", (stream,))
        skill_rows = {
            r["code"]: r["id"]
            for r in fetch_all("select id, code from skills where stream = %s", (stream,))
        }
        for code, resources in cfg.get("learning_resources", {}).items():
            sid = skill_rows.get(code)
            if not sid:
                continue
            for r in resources:
                cur.execute(
                    """
                    insert into learning_resources
                        (stream, skill_id, title, provider, url, duration_hours, is_free)
                    values (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (stream, sid, r["title"], r["provider"], r["url"],
                     r.get("duration_hours", 4), r.get("is_free", True)),
                )
    return count


def _embed_skills(stream: str) -> bool:
    if embeddings.provider_name() != "fastembed":
        return False
    rows = fetch_all(
        "select id, label, aliases from skills where stream = %s", (stream,)
    )
    texts = [f"{r['label']}. {' '.join(r['aliases'] or [])}" for r in rows]
    vecs = embeddings.embed_texts(texts)
    if vecs is None:
        return False
    with transaction() as cur:
        for r, v in zip(rows, vecs):
            cur.execute(
                "update skills set embedding = %s::vector, embedding_provider = %s where id = %s",
                (embeddings.vec_literal(v), "fastembed", r["id"]),
            )
    return True


def _get_role_id(name: str) -> str:
    return str(fetch_one("select id from roles_permissions where name = %s", (name,))["id"])


def _create_user(rnd_email: str, full_name: str, role: str, password: str,
                 institution_id: str | None = None, organization_id: str | None = None,
                 consent: bool = False) -> dict:
    row = execute(
        """
        insert into users (email, full_name, password_hash, role_id, institution_id,
                           organization_id, consent_given, consent_at)
        values (%s, %s, %s, %s, %s, %s, %s, case when %s then now() else null end)
        returning id, email
        """,
        (rnd_email, full_name, hash_password(password), _get_role_id(role),
         institution_id, organization_id, consent, consent),
    )
    return row


def _add_skill_claim(profile_id: str, skill_id: str, state: str, user_ids: dict,
                     seq: int, extracted: bool = True) -> None:
    claimed_at = STATE_TIMESTAMP_BASE + timedelta(hours=seq)
    cosigned_at = claimed_at + timedelta(days=1) if state != "claimed" else None
    verified_at = claimed_at + timedelta(days=3) if state == "verified" else None
    execute(
        """
        insert into skill_verification_state
            (student_profile_id, skill_id, state, extracted_from_resume, claimed_at,
             claimed_by, cosigned_at, cosigned_by, verified_at, verified_by)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (profile_id, skill_id, state, extracted, claimed_at, user_ids.get("student"),
         cosigned_at, user_ids.get("tpo") if cosigned_at else None,
         verified_at, user_ids.get("industry") if verified_at else None),
    )


def _make_student(rnd: random.Random, idx: int, cfg: dict, stream: str,
                  inst_id: str, tpo_user_id: str, industry_user_id: str) -> dict:
    first = rnd.choice(FIRST_NAMES)
    last = rnd.choice(LAST_NAMES)
    email = f"{first.lower()}.{last.lower()}.{idx}@student.example.edu"
    user = _create_user(email, f"{first} {last}", "student", DEMO_PASSWORD,
                        institution_id=inst_id, consent=True)
    role = rnd.choice(cfg["target_roles"])
    req_codes = [r["code"] for r in role["required"]]
    all_codes = [s["code"] for s in cfg["skills"]]
    n_skills = rnd.randint(6, 10)
    chosen = set()
    for c in req_codes:
        if rnd.random() < 0.75:
            chosen.add(c)
    while len(chosen) < min(n_skills, len(all_codes)):
        chosen.add(rnd.choice(all_codes))
    chosen = list(chosen)
    rnd.shuffle(chosen)

    bullets = []
    skill_lines = []
    for c in chosen:
        skill_cfg = next(s for s in cfg["skills"] if s["code"] == c)
        template = rnd.choice(cfg["generator"]["resume_bullets"])
        phrase = skill_cfg["label"]
        bullets.append("- " + template.format(skill=phrase))
        skill_lines.append(phrase)
    resume = (
        f"{first} {last} — {cfg['name']} student, class of {rnd.choice([2026, 2027])}.\n"
        f"Key skills: {', '.join(skill_lines)}.\nProjects & experience:\n"
        + "\n".join(bullets)
    )

    profile = execute(
        """
        insert into student_profiles (user_id, institution_id, stream, resume_text,
            cgpa, graduation_year, consent_given, consent_at, extraction_status)
        values (%s, %s, %s, %s, %s, %s, true, now(), 'pending')
        returning id
        """,
        (user["id"], inst_id, stream, resume, round(rnd.uniform(6.2, 9.4), 1),
         rnd.choice([2026, 2026, 2027])),
    )
    profile_id = str(profile["id"])
    state_user_ids = {"student": user["id"], "tpo": tpo_user_id, "industry": industry_user_id}
    for i, c in enumerate(chosen):
        r = rnd.random()
        state = "claimed" if r < 0.55 else ("institution_cosigned" if r < 0.85 else "verified")
        skill = fetch_one("select id from skills where stream = %s and code = %s", (stream, c))
        _add_skill_claim(profile_id, str(skill["id"]), state, state_user_ids, seq=idx * 10 + i)
    return {"profile_id": profile_id, "user_id": str(user["id"]), "name": f"{first} {last}"}


def _make_jd(rnd: random.Random, org_id: str, template: dict, cfg: dict,
             stream: str, posted_by: str | None) -> str:
    role_cfg = next(r for r in cfg["target_roles"] if r["name"] == template["role"])
    codes = [r["code"] for r in role_cfg["required"]]
    skill_cfgs = [next(s for s in cfg["skills"] if s["code"] == c) for c in codes]
    labels = ", ".join(s["label"] for s in skill_cfgs[:4])
    alias_phrase = rnd.choice(skill_cfgs[0]["aliases"] or [skill_cfgs[0]["label"]])
    intro = rnd.choice(cfg["generator"]["jd_intro"])
    outro = rnd.choice(cfg["generator"]["jd_outro"])
    description = (
        f"{intro} The {template['title']} will work hands-on with {labels}. "
        f"You should be comfortable with {alias_phrase} and eager to learn the rest of our stack. {outro}"
    )
    kind = template.get("kind", "internship")
    stipend = rnd.randint(*template["stipend"]) if template.get("stipend") else None
    smin = rnd.randint(*template["salary_min"]) if template.get("salary_min") else None
    smax = rnd.randint(*template["salary_max"]) if template.get("salary_max") else None
    row = execute(
        """
        insert into job_descriptions (organization_id, posted_by_user_id, title, kind,
            stream, description, location, stipend, salary_min, salary_max, seats, is_synthetic)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
        returning id
        """,
        (org_id, posted_by, template["title"], kind, stream, description,
         rnd.choice(["Bengaluru", "Pune", "Hyderabad", "Remote (India)"]),
         stipend, smin, smax, rnd.randint(*template.get("seats", [1, 3]))),
    )
    return str(row["id"])


def generate_stream(stream: str, wipe: bool = True, students_per_institution: int = 16,
                    seed: int = 42, note: str | None = None) -> dict:
    """Seed one stream end-to-end. Deterministic for a given seed."""
    cfg = stream_config(stream)
    rnd = _rnd_for(stream, seed)
    provider = embeddings.provider_name()

    if wipe:
        with transaction() as cur:
            # Stream-scoped deletes in FK-safe order
            cur.execute(
                "delete from outcomes where application_id in (select id from applications "
                "where student_profile_id in (select id from student_profiles where stream = %s))",
                (stream,),
            )
            cur.execute(
                "delete from applications where student_profile_id in "
                "(select id from student_profiles where stream = %s)", (stream,)
            )
            cur.execute(
                "delete from matches where student_profile_id in "
                "(select id from student_profiles where stream = %s)", (stream,)
            )
            cur.execute(
                "delete from skill_verification_state where student_profile_id in "
                "(select id from student_profiles where stream = %s)", (stream,)
            )
            # Delete the stream's student users BEFORE their profiles, so the
            # skill_verification_state FK on users is satisfied.
            cur.execute(
                "delete from users where id in (select user_id from student_profiles "
                "where stream = %s)", (stream,)
            )
            cur.execute("delete from student_profiles where stream = %s", (stream,))
            cur.execute("delete from curriculum_gap_signal where stream = %s", (stream,))
            cur.execute("delete from learning_resources where stream = %s", (stream,))
            cur.execute("delete from skills where stream = %s", (stream,))
            cur.execute("delete from job_descriptions where stream = %s", (stream,))
            cur.execute("delete from seed_runs where stream = %s", (stream,))
            # users: delete the stream's demo accounts (students, tpo, industry).
            # NOTE: student.demo / student.demo2 are CSE-only demo accounts and must
            # NOT be deleted when reseeding another stream (their verification
            # state rows in CSE reference them).
            demo_emails = [
                f"student.{stream}.demo@sih.gov.in",
                f"tpo.{stream}.demo@sih.gov.in",
                f"industry.{stream}.demo@sih.gov.in",
            ]
            if stream == "cse":
                demo_emails = [
                    "student.demo@sih.gov.in",
                    "student.demo2@sih.gov.in",
                ] + demo_emails
            for demo_email in demo_emails:
                cur.execute("delete from users where email = %s", (demo_email,))

    n_skills = _upsert_taxonomy(stream, cfg)
    embedded = _embed_skills(stream)

    # institutions & organizations (synthetic) — upsert so cross-stream data survives
    inst_ids = {}
    for inst in INSTITUTIONS.get(stream, []):
        existing = fetch_one(
            "select id from institutions where name = %s and stream = %s",
            (inst["name"], stream),
        )
        if existing:
            inst_ids[inst["name"]] = str(existing["id"])
        else:
            row = execute(
                "insert into institutions (name, stream, city, is_synthetic) values (%s,%s,%s,true) returning id",
                (inst["name"], stream, inst["city"]),
            )
            inst_ids[inst["name"]] = str(row["id"])

    org_ids = {}
    for org_name in cfg["generator"]["orgs"]:
        existing = fetch_one("select id from organizations where name = %s", (org_name,))
        if existing:
            org_ids[org_name] = str(existing["id"])
        else:
            row = execute(
                "insert into organizations (name, industry, is_synthetic) values (%s, %s, true) returning id",
                (org_name, cfg["name"]),
            )
            org_ids[org_name] = str(row["id"])

    # demo accounts
    admin = fetch_one("select id, email from users where email = %s", (ADMIN_EMAIL,))
    if admin is None:
        admin = _create_user(ADMIN_EMAIL, "Ministry Demo Admin", "admin", DEMO_PASSWORD)

    first_inst = list(INSTITUTIONS.get(stream, [None]))[0]
    first_inst_id = inst_ids.get(first_inst["name"]) if first_inst else None
    primary_org = cfg["generator"]["orgs"][0]

    tpo_user = _create_user(
        f"tpo.{stream}.demo@sih.gov.in", f"TPO {cfg['name']}", "tpo", DEMO_PASSWORD,
        institution_id=first_inst_id,
    )
    industry_user = _create_user(
        f"industry.{stream}.demo@sih.gov.in", f"Industry {primary_org}", "industry",
        DEMO_PASSWORD, organization_id=org_ids[primary_org],
    )

    # demo students (CSE gets the crafted semantic-proof pair; other streams
    # get one straightforward demo student)
    demo_students = []
    if stream == "cse":
        for spec in (DEMO_SEMANTIC, DEMO_LITERAL):
            user = _create_user(spec["email"], f"{spec['first']} {spec['last']}", "student",
                                DEMO_PASSWORD, institution_id=first_inst_id, consent=True)
            profile = execute(
                """
                insert into student_profiles (user_id, institution_id, stream, resume_text,
                    cgpa, graduation_year, consent_given, consent_at, extraction_status)
                values (%s, %s, %s, %s, %s, 2026, true, now(), 'pending')
                returning id
                """,
                (user["id"], first_inst_id, stream, spec["resume"], spec["cgpa"]),
            )
            state_user_ids = {"student": user["id"], "tpo": tpo_user["id"],
                              "industry": industry_user["id"]}
            for i, (code, state) in enumerate(spec["skills"].items()):
                skill = fetch_one("select id from skills where stream=%s and code=%s", (stream, code))
                if skill:
                    _add_skill_claim(str(profile["id"]), str(skill["id"]), state,
                                     state_user_ids, seq=len(demo_students) * 10 + i)
            demo_students.append({
                "profile_id": str(profile["id"]),
                "email": spec["email"],
                "kind": "semantic-proof" if spec is DEMO_SEMANTIC else "literal-twin",
            })
    else:
        user = _create_user(f"student.{stream}.demo@sih.gov.in", "Demo Student", "student",
                            DEMO_PASSWORD, institution_id=first_inst_id, consent=True)
        profile = execute(
            """
            insert into student_profiles (user_id, institution_id, stream, resume_text,
                cgpa, graduation_year, consent_given, consent_at, extraction_status)
            values (%s, %s, %s, %s, 8.3, 2026, true, now(), 'pending')
            returning id
            """,
            (user["id"], first_inst_id, stream,
             f"Passionate {cfg['name']} student with hands-on lab experience across "
             f"{', '.join(s['label'] for s in cfg['skills'][:5])}."),
        )
        demo_students.append({"profile_id": str(profile["id"]),
                              "email": user["email"], "kind": "demo"})

    # random students per institution
    n_random = 0
    for inst_name, inst_id in inst_ids.items():
        for i in range(students_per_institution):
            _make_student(rnd, i, cfg, stream, inst_id, tpo_user["id"], industry_user["id"])
            n_random += 1

    # process all student profiles (extraction + embeddings)
    profiles = fetch_all("select id from student_profiles where stream = %s", (stream,))
    for p in profiles:
        process_student_profile(str(p["id"]))

    # job descriptions
    jd_ids = []
    for org_name in cfg["generator"]["orgs"]:
        templates = [t for t in cfg["generator"]["jd_templates"] if True]
        n_jds = min(3, len(templates))
        for t in rnd.sample(templates, n_jds):
            jd_ids.append(_make_jd(rnd, org_ids[org_name], t, cfg, stream,
                                   industry_user["id"] if org_name == primary_org else None))
    if stream == "cse":
        # JD A — the semantic-proof target at CloudNest, posted by the demo industry user
        row = execute(
            """
            insert into job_descriptions (organization_id, posted_by_user_id, title, kind,
                stream, description, location, stipend, seats, is_synthetic)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, true)
            returning id
            """,
            (org_ids[JD_A["org"]], industry_user["id"], JD_A["title"], JD_A["kind"],
             stream, JD_A["description"], JD_A["location"], JD_A["stipend"], JD_A["seats"]),
        )
        jd_a_id = str(row["id"])
        jd_ids.insert(0, jd_a_id)
    for jid in jd_ids:
        process_job_description(jid)  # extracts skills, embeds, computes matches for all students

    # applications
    n_apps = 0
    app_ids = []
    for p in profiles:
        pid = str(p["id"])
        if rnd.random() < 0.35:
            continue  # some students haven't applied yet
        top = fetch_one(
            """
            select m.id as match_id, m.job_description_id, m.score from matches m
            join job_descriptions jd on jd.id = m.job_description_id
            where m.student_profile_id = %s and jd.status = 'open'
            order by m.score desc limit 1
            """,
            (pid,),
        )
        if top is None:
            continue
        score = float(top["score"])
        status = "applied"
        r = rnd.random()
        if score >= 70 and r < 0.45:
            status = "selected"
        elif score >= 55 and r < 0.6:
            status = "shortlisted"
        app = execute(
            """
            insert into applications (student_profile_id, job_description_id, match_id, status)
            values (%s, %s, %s, %s) returning id
            """,
            (pid, str(top["job_description_id"]), str(top["match_id"]), status),
        )
        app_ids.append((str(app["id"]), status, score))
        n_apps += 1

    # demo student applies to JD A via the real loop
    if stream == "cse":
        demo_profile_id = demo_students[0]["profile_id"]
        jd_a = fetch_one("select id from job_descriptions where id = %s", (jd_a_id,))
        existing = fetch_one(
            "select id from applications where student_profile_id = %s and job_description_id = %s",
            (demo_profile_id, jd_a_id),
        )
        if not existing:
            m = fetch_one(
                "select id, score from matches where student_profile_id = %s and job_description_id = %s",
                (demo_profile_id, jd_a_id),
            )
            app = execute(
                """
                insert into applications (student_profile_id, job_description_id, match_id, status, cover_note)
                values (%s, %s, %s, 'shortlisted', %s) returning id
                """,
                (demo_profile_id, jd_a_id, str(m["id"]) if m else None,
                 "Excited about your platform; my fest registration portal work maps well to this role."),
            )
            app_ids.append((str(app["id"]), "shortlisted", float(m["score"]) if m else 0))
            n_apps += 1

    # outcomes (triggers recalibration + curriculum signals per outcome)
    n_outcomes = 0
    eligible = [a for a in app_ids if a[1] in ("selected", "shortlisted")]
    rnd.shuffle(eligible)
    for app_id, status, score in eligible[:14]:
        r = rnd.random()
        if r < 0.55:
            result, rating = "completed", rnd.randint(3, 5)
        elif r < 0.75:
            result, rating = "hired", rnd.randint(3, 5)
        else:
            result, rating = "dropped", rnd.randint(1, 2)
        outcome = execute(
            """
            insert into outcomes (application_id, job_description_id, student_profile_id,
                result, performance_rating, industry_feedback, is_synthetic)
            select a.id, a.job_description_id, a.student_profile_id, %s, %s, %s, true
            from applications a where a.id = %s
            on conflict (application_id) do nothing
            returning id
            """,
            (result, rating,
             rnd.choice([
                 "Solid contributor, communicated well.",
                 "Delivered on time; needs depth in edge cases.",
                 "Struggled with the core workload despite interview signals.",
                 "Excellent — exceeded expectations for an intern.",
             ]),
             app_id),
        )
        if outcome:
            apply_outcome_recalibration(str(outcome["id"]))
            n_outcomes += 1
        execute(
            "update applications set status = case when %s = 'hired' then 'selected' else status end where id = %s",
            (result, app_id),
        )

    # final pass: matches reflect recalibrated weights; signals fresh
    from app.services.matching import compute_matches_for_stream

    compute_matches_for_stream(stream)
    for inst_id in inst_ids.values():
        rebuild_curriculum_signals(inst_id)

    execute(
        "insert into seed_runs (stream, note, is_synthetic) values (%s, %s, true)",
        (stream, note or "Deterministic synthetic seed"),
    )

    return {
        "stream": stream,
        "provider": provider,
        "skills": n_skills,
        "skill_embeddings_stored": embedded,
        "institutions": len(inst_ids),
        "organizations": len(org_ids),
        "students": len(profiles),
        "job_descriptions": len(jd_ids),
        "applications": n_apps,
        "outcomes": n_outcomes,
        "demo_accounts": {
            "admin": ADMIN_EMAIL,
            "student": DEMO_SEMANTIC["email"] if stream == "cse" else f"student.{stream}.demo@sih.gov.in",
            "student_literal_twin": DEMO_LITERAL["email"] if stream == "cse" else None,
            "tpo": f"tpo.{stream}.demo@sih.gov.in",
            "industry": f"industry.{stream}.demo@sih.gov.in",
            "password": DEMO_PASSWORD,
        },
        "synthetic": True,
    }
