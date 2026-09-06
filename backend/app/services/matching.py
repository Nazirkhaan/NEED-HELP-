"""Matching engine with explainability payloads.

Score = 0.55 * semantic + 0.45 * taxonomy
  - semantic: pgvector cosine between student aggregate embedding and JD
    aggregate embedding (fastembed path), or TF-IDF cosine over skill text
    when the embedding model is unavailable.
  - taxonomy: demand-weighted coverage of the JD's skills by the student's
    claimed/co-signed/verified skills (verification state affects the credit).

Every match stores matched_skills + missing_skills + literal keyword overlap,
so the UI can render the full skill-diff and prove semantic (not keyword)
matching.
"""
import math

from app.db.pool import fetch_all, fetch_one, transaction
from app.services import embeddings
from app.services.tfidf import literal_token_overlap

STATE_FACTOR = {"verified": 1.0, "institution_cosigned": 0.9, "claimed": 0.7}

W_SEMANTIC = 0.55
W_TAXONOMY = 0.45


def _student_payload(student_profile_id: str) -> dict | None:
    profile = fetch_one(
        "select * from student_profiles where id = %s", (student_profile_id,)
    )
    if profile is None:
        return None
    skills = fetch_all(
        """
        select s.id, s.code, s.label, s.category, s.aliases, s.demand_weight,
               v.state
        from skill_verification_state v
        join skills s on s.id = v.skill_id
        where v.student_profile_id = %s
        """,
        (student_profile_id,),
    )
    return {"profile": profile, "skills": skills}


def _student_skill_text(skills: list[dict]) -> str:
    parts = []
    for s in skills:
        parts.append(s["label"])
        parts.extend(s["aliases"] or [])
    return ". ".join(parts)


def _semantic_scores_sql(stream: str, student_profile_id: str) -> dict[str, float]:
    """pgvector cosine between the student aggregate embedding and every open
    JD aggregate embedding in the stream, in a single query."""
    rows = fetch_all(
        """
        select jd.id, 1 - (sp.embedding <=> jd.embedding) as sim
        from student_profiles sp
        join job_descriptions jd on jd.stream = %s
            and jd.status = 'open'
            and jd.embedding is not null
        where sp.id = %s and sp.embedding is not null
        """,
        (stream, student_profile_id),
    )
    return {str(r["id"]): float(r["sim"]) for r in rows}


def _semantic_scores_tfidf(student: dict, jds: list[dict]) -> dict[str, float]:
    """Fallback: TF-IDF cosine between student skill text and JD skill text."""
    from app.services.tfidf import TfidfIndex

    s_text = _student_skill_text(student["skills"])
    scores: dict[str, float] = {}
    for jd in jds:
        jd_skills = jd["extracted_skills"] or []
        jd_text = ". ".join(
            f"{e.get('label', '')} {e.get('label', '')}" for e in jd_skills
        )
        if not s_text or not jd_text:
            scores[str(jd["id"])] = 0.0
            continue
        idx = TfidfIndex([s_text, jd_text])
        scores[str(jd["id"])] = TfidfIndex.cosine(
            idx.transform(s_text), idx.transform(jd_text)
        )
    return scores


def _taxonomy_components(student: dict, jd: dict) -> tuple[float, list[dict], list[dict], list[dict]]:
    """Returns (taxonomy_score, matched, missing, extra) for one JD."""
    student_map = {str(s["id"]): s for s in student["skills"]}
    skill_weights = {str(s["id"]): float(s["demand_weight"]) for s in student["skills"]}
    # demand_weight of skills only present in the JD must come from the taxonomy
    jd_skill_ids = [str(e["skill_id"]) for e in (jd["extracted_skills"] or [])]
    if jd_skill_ids:
        for r in fetch_all(
            "select id, demand_weight from skills where id = any(%s)",
            (jd_skill_ids,),
        ):
            skill_weights[str(r["id"])] = float(r["demand_weight"])

    matched, missing, extra = [], [], []
    num = den = 0.0
    seen = set(student_map)

    for entry in jd["extracted_skills"] or []:
        sid = str(entry["skill_id"])
        w = float(entry.get("weight", 1.0)) * skill_weights.get(sid, 1.0)
        den += w
        if sid in student_map:
            factor = STATE_FACTOR.get(student_map[sid]["state"], 0.7)
            num += w * factor
            matched.append(
                {
                    "skill_id": sid,
                    "code": entry.get("code"),
                    "label": entry.get("label"),
                    "jd_weight": float(entry.get("weight", 1.0)),
                    "demand_weight": skill_weights.get(sid, 1.0),
                    "student_state": student_map[sid]["state"],
                    "credit": round(factor, 2),
                }
            )
        else:
            missing.append(
                {
                    "skill_id": sid,
                    "code": entry.get("code"),
                    "label": entry.get("label"),
                    "jd_weight": float(entry.get("weight", 1.0)),
                    "demand_weight": skill_weights.get(sid, 1.0),
                    "weighted_gap": round(w, 3),
                }
            )

    for s in student["skills"]:
        if str(s["id"]) not in {m["skill_id"] for m in matched}:
            extra.append(
                {
                    "skill_id": str(s["id"]),
                    "code": s["code"],
                    "label": s["label"],
                    "student_state": s["state"],
                }
            )

    matched.sort(key=lambda m: -(m["jd_weight"] * m["demand_weight"]))
    missing.sort(key=lambda m: -m["weighted_gap"])
    score = num / den if den > 0 else 0.0
    return score, matched, missing, extra[:10]


def compute_match_for_student_jd(student: dict, jd: dict, semantic_map: dict[str, float]) -> dict:
    tax_score, matched, missing, extra = _taxonomy_components(student, jd)
    provider = embeddings.provider_name()
    sem_score = semantic_map.get(str(jd["id"]))
    if sem_score is None:
        # TF-IDF fallback (also the path when one side lacks an embedding)
        from app.services.tfidf import TfidfIndex

        jd_skills = jd["extracted_skills"] or []
        jd_text = ". ".join(f"{e.get('label', '')}" for e in jd_skills)
        s_text = _student_skill_text(student["skills"])
        idx = TfidfIndex([s_text, jd_text])
        sem_score = TfidfIndex.cosine(idx.transform(s_text), idx.transform(jd_text))
        provider = "tfidf"

    score = W_SEMANTIC * sem_score + W_TAXONOMY * tax_score
    resume_text = student["profile"]["resume_text"] or ""
    literal = literal_token_overlap(resume_text, jd["description"])

    payload = {
        "student_profile_id": str(student["profile"]["id"]),
        "job_description_id": str(jd["id"]),
        "score": round(score * 100, 1),
        "semantic_score": round(sem_score * 100, 1),
        "taxonomy_score": round(tax_score * 100, 1),
        "provider": provider,
        "matched_skills": matched,
        "missing_skills": missing,
        "extra_skills": extra,
        "literal_keyword_overlap": round(literal * 100, 1),
    }
    return payload


def upsert_match(payload: dict) -> None:
    import json

    with transaction() as cur:
        cur.execute(
            """
            insert into matches (student_profile_id, job_description_id, score,
                semantic_score, taxonomy_score, provider, matched_skills,
                missing_skills, extra_skills, literal_keyword_overlap)
            values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            on conflict (student_profile_id, job_description_id) do update set
                score = excluded.score,
                semantic_score = excluded.semantic_score,
                taxonomy_score = excluded.taxonomy_score,
                provider = excluded.provider,
                matched_skills = excluded.matched_skills,
                missing_skills = excluded.missing_skills,
                extra_skills = excluded.extra_skills,
                literal_keyword_overlap = excluded.literal_keyword_overlap,
                created_at = now()
            """,
            (
                payload["student_profile_id"], payload["job_description_id"],
                payload["score"], payload["semantic_score"], payload["taxonomy_score"],
                payload["provider"],
                json.dumps(payload["matched_skills"]),
                json.dumps(payload["missing_skills"]),
                json.dumps(payload["extra_skills"]),
                payload["literal_keyword_overlap"],
            ),
        )


def compute_matches_for_student(student_profile_id: str, jd_id: str | None = None) -> int:
    student = _student_payload(student_profile_id)
    if student is None:
        return 0
    stream = student["profile"]["stream"]
    if jd_id:
        jds = fetch_all(
            "select * from job_descriptions where id = %s and status = 'open'", (jd_id,)
        )
    else:
        jds = fetch_all(
            "select * from job_descriptions where stream = %s and status = 'open' order by created_at",
            (stream,),
        )
    if not jds:
        return 0
    semantic_map = _semantic_scores_sql(stream, student_profile_id)
    count = 0
    for jd in jds:
        payload = compute_match_for_student_jd(student, jd, semantic_map)
        upsert_match(payload)
        count += 1
    return count


def compute_matches_for_stream(stream: str, student_ids: list[str] | None = None) -> int:
    if student_ids is None:
        rows = fetch_all("select id from student_profiles where stream = %s", (stream,))
        student_ids = [str(r["id"]) for r in rows]
    total = 0
    for sid in student_ids:
        total += compute_matches_for_student(sid)
    return total


def top_matches_for_student(student_profile_id: str, limit: int = 20) -> list[dict]:
    return fetch_all(
        """
        select m.*, jd.title, jd.kind, jd.location, jd.stipend, jd.salary_min,
               jd.salary_max, o.name as organization_name, jd.stream,
               a.id as application_id, a.status as application_status
        from matches m
        join job_descriptions jd on jd.id = m.job_description_id
        join organizations o on o.id = jd.organization_id
        left join applications a on a.student_profile_id = m.student_profile_id
            and a.job_description_id = m.job_description_id
        where m.student_profile_id = %s and jd.status = 'open'
        order by m.score desc
        limit %s
        """,
        (student_profile_id, limit),
    )
