"""Public metadata: streams, target roles, taxonomy, embedding provider."""
from fastapi import APIRouter, HTTPException, Query

from app.db.pool import afetch_all
from app.services import embeddings
from app.services.config_loader import list_streams, stream_config

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/streams")
async def streams():
    out = []
    for s in list_streams():
        try:
            cfg = stream_config(s["key"])
        except FileNotFoundError:
            continue
        out.append({
            "key": s["key"],
            "name": s["name"],
            "n_skills": len(cfg["skills"]),
            "target_roles": [r["name"] for r in cfg["target_roles"]],
        })
    return out


@router.get("/skills")
async def skills(stream: str = Query(...)):
    try:
        cfg = stream_config(stream)
    except FileNotFoundError:
        raise HTTPException(404, f"unknown stream '{stream}'")
    rows = await afetch_all(
        "select id, code, label, category, demand_weight from skills "
        "where stream = %s and active order by category, label",
        (stream,),
    )
    for r in rows:
        r["id"] = str(r["id"])
        r["demand_weight"] = float(r["demand_weight"])
    return rows


@router.get("/provider")
async def provider_info():
    return {
        "provider": embeddings.provider_name(),
        "dim": 384,
        "model": "sentence-transformers/all-MiniLM-L6-v2 (fastembed/ONNX)" if embeddings.provider_name() == "fastembed" else "TF-IDF fallback (pure Python)",
    }
