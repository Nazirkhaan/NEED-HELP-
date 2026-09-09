"""Skill extraction from free text (resumes / job descriptions).

Deterministic two-layer pipeline — NO live LLM calls at request time:
  1. Alias scan against the config-driven taxonomy (instant, exact).
  2. Semantic layer via pgvector cosine against precomputed skill embeddings
     (only when local fastembed model is available; skipped otherwise).
"""
import re

from app.db.pool import afetch_all
from app.services import embeddings

_SKILL_LIMIT = 12
_SEMANTIC_THRESHOLD = 0.45


def _alias_hit(text_lower: str, candidate: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(candidate.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, text_lower) is not None


async def extract_skills(text: str, stream: str, use_semantic: bool = True) -> list[dict]:
    """Return [{skill_id, code, label, category, confidence, source}]."""
    if not text or not text.strip():
        return []
    skills = await afetch_all(
        "select id, code, label, category, aliases from skills "
        "where stream = %s and active order by label",
        (stream,),
    )
    text_lower = text.lower()
    found: dict[str, dict] = {}

    for s in skills:
        candidates = [s["label"]] + list(s["aliases"] or [])
        for cand in candidates:
            if cand and _alias_hit(text_lower, cand):
                found[str(s["id"])] = {
                    "skill_id": str(s["id"]),
                    "code": s["code"],
                    "label": s["label"],
                    "category": s["category"],
                    "confidence": 1.0,
                    "source": "alias",
                }
                break

    if use_semantic and embeddings.provider_name() == "fastembed":
        qvec = embeddings.embed_one(text[:6000])
        if qvec:
            rows = await afetch_all(
                """
                select id, code, label, category,
                       1 - (embedding <=> %s::vector) as sim
                from skills
                where stream = %s and active and embedding is not null
                order by embedding <=> %s::vector
                limit %s
                """,
                (embeddings.vec_literal(qvec), stream, embeddings.vec_literal(qvec), _SKILL_LIMIT),
            )
            for r in rows:
                sid = str(r["id"])
                sim = float(r["sim"])
                if sim < _SEMANTIC_THRESHOLD or sid in found:
                    continue
                found[sid] = {
                    "skill_id": sid,
                    "code": r["code"],
                    "label": r["label"],
                    "category": r["category"],
                    # semantic hits carry lower confidence than exact alias hits
                    "confidence": round(0.5 + min(0.35, (sim - _SEMANTIC_THRESHOLD) * 1.4), 2),
                    "source": "semantic",
                }

    return sorted(found.values(), key=lambda x: (-x["confidence"], x["label"]))


async def extract_with_weights(text: str, stream: str) -> tuple[list[dict], str]:
    """Extraction returning JD-ready skill entries with demand weights, plus
    the provider name used. Returns ([{skill_id, code, label, weight}], provider)."""
    found = await extract_skills(text, stream)
    if not found:
        return [], embeddings.provider_name()
    ids = tuple(f["skill_id"] for f in found)
    weights = {
        str(r["id"]): float(r["demand_weight"])
        for r in await afetch_all(
            "select id, demand_weight from skills where id = any(%s)", (list(ids),)
        )
    }
    out = [
        {
            "skill_id": f["skill_id"],
            "code": f["code"],
            "label": f["label"],
            "weight": round(weights.get(f["skill_id"], 1.0), 3),
        }
        for f in found
    ]
    return out, embeddings.provider_name()
