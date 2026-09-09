"""Profile / JD processing pipeline: extraction -> embeddings -> matches.

Both student profiles and job descriptions are processed the same way:
extract skills, build an aggregate embedding (text + skill vector blend),
persist it to pgvector, then (re)compute matches. Embeddings are fully local;
if the model is unavailable, extraction still works via the alias layer and
matching falls back to TF-IDF.
"""
from app.db.pool import aexecute, afetch_all, afetch_one, atransaction
from app.services import embeddings, extraction, matching
from app.services.matching import STATE_FACTOR

SKILL_W = 0.4
TEXT_W = 0.6


def _blend(text_vec: list[float] | None, skill_vecs: list[tuple[list[float], float]]) -> list[float] | None:
    """Weighted blend of a document embedding and its skill embeddings."""
    if not text_vec and not skill_vecs:
        return None
    acc = [0.0] * len(text_vec or skill_vecs[0][0])
    total = 0.0
    if text_vec:
        for i, x in enumerate(text_vec):
            acc[i] += TEXT_W * x
        total += TEXT_W
    if skill_vecs:
        wsum = sum(w for _, w in skill_vecs)
        if wsum > 0:
            for i in range(len(acc)):
                acc[i] += SKILL_W * sum(v[i] * w for v, w in skill_vecs) / wsum
            total += SKILL_W
    if total == 0:
        return None
    norm = math_sqrt(sum(x * x for x in acc)) or 1.0
    return [x / norm for x in acc]


def math_sqrt(x: float) -> float:
    import math
    return math.sqrt(x)


async def _skill_vectors(skill_ids: list[str], state_weights: dict[str, float] | None = None) -> list[tuple[list[float], float]]:
    if not skill_ids:
        return []
    rows = await afetch_all(
        "select id, embedding from skills where id = any(%s) and embedding is not null",
        (skill_ids,),
    )
    out = []
    for r in rows:
        vec = embeddings.parse_vector(r["embedding"])
        if vec is None:
            continue
        w = 1.0
        if state_weights:
            w = state_weights.get(str(r["id"]), 1.0)
        if w > 0:
            out.append((vec, w))
    return out


async def process_student_profile(student_profile_id: str) -> dict:
    """Extract skills from resume text, store claims, embed, recompute matches."""
    profile = await afetch_one("select * from student_profiles where id = %s", (student_profile_id,))
    if profile is None:
        raise ValueError("student profile not found")
    stream = profile["stream"]
    resume_text = profile["resume_text"] or ""

    extracted = await extraction.extract_skills(resume_text, stream)
    provider = embeddings.provider_name()

    if extracted:
        async with atransaction() as cur:
            for f in extracted:
                await cur.execute(
                    """
                    insert into skill_verification_state
                        (student_profile_id, skill_id, state, extracted_from_resume)
                    values (%s, %s, 'claimed', true)
                    on conflict (student_profile_id, skill_id) do nothing
                    """,
                    (student_profile_id, f["skill_id"]),
                )

    state_weights = {
        str(r["skill_id"]): STATE_FACTOR.get(r["state"], 0.7)
        for r in await afetch_all(
            "select skill_id, state from skill_verification_state where student_profile_id = %s",
            (student_profile_id,),
        )
    }
    skill_ids = list(state_weights.keys())
    text_vec = embeddings.embed_one(resume_text[:6000]) if provider == "fastembed" else None
    svecs = await _skill_vectors(skill_ids, state_weights) if provider == "fastembed" else []
    vec = _blend(text_vec, svecs) if provider == "fastembed" else None

    await aexecute(
        """
        update student_profiles set extraction_status = %s, embedding = %s::vector,
            embedding_provider = %s, updated_at = now() where id = %s
        """,
        ("extracted" if extracted else "empty",
         embeddings.vec_literal(vec) if vec else None, provider, student_profile_id),
    )

    n_matches = await matching.compute_matches_for_student(student_profile_id)
    return {
        "student_profile_id": student_profile_id,
        "extracted_count": len(extracted),
        "skills": extracted,
        "embedding_stored": vec is not None,
        "provider": provider,
        "matches_computed": n_matches,
    }


async def process_job_description(jd_id: str) -> dict:
    """Extract skills from the JD text, store them, embed, compute matches
    against every open student in the stream."""
    jd = await afetch_one("select * from job_descriptions where id = %s", (jd_id,))
    if jd is None:
        raise ValueError("job description not found")
    stream = jd["stream"]

    skills, provider = await extraction.extract_with_weights(jd["description"], stream)
    await aexecute(
        "update job_descriptions set extracted_skills = %s::jsonb, extraction_status = %s "
        "where id = %s",
        (_dumps(skills), "extracted" if skills else "empty", jd_id),
    )

    vec = None
    if provider == "fastembed":
        text_vec = embeddings.embed_one((jd["description"] or "")[:6000])
        svecs = await _skill_vectors([s["skill_id"] for s in skills])
        vec = _blend(text_vec, svecs)
        await aexecute(
            "update job_descriptions set embedding = %s::vector, embedding_provider = %s "
            "where id = %s",
            (embeddings.vec_literal(vec) if vec else None, provider, jd_id),
        )

    students = await afetch_all("select id from student_profiles where stream = %s", (stream,))
    n = 0
    for st in students:
        await matching.compute_matches_for_student(str(st["id"]), jd_id=jd_id)
        n += 1
    return {
        "job_description_id": jd_id,
        "extracted_count": len(skills),
        "skills": skills,
        "embedding_stored": vec is not None,
        "provider": provider,
        "students_matched": n,
    }


def _dumps(obj) -> str:
    import json
    return json.dumps(obj)
