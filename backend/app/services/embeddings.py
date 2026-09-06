"""Local embedding providers with graceful degradation.

Provider chain (first available wins):
  1. fastembed (ONNX MiniLM-L6-v2, 384-dim, fully local, no torch)
  2. TF-IDF fallback (pure Python) — always available, no network

No request-time network calls: the fastembed model is loaded from the local
HF cache; if it is missing we fall back instead of downloading mid-request.
"""
import threading

from app.config import settings
from app.services.tfidf import TfidfIndex

_DIM = 384
_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_lock = threading.Lock()
_model = None
_model_failed = False


def provider_name() -> str:
    if settings.embedding_provider == "tfidf":
        return "tfidf"
    return "fastembed" if _fastembed_available() else "tfidf"


def _fastembed_available() -> bool:
    if settings.embedding_provider == "tfidf":
        return False
    global _model, _model_failed
    if _model is not None:
        return True
    if _model_failed:
        return False
    with _lock:
        if _model is None and not _model_failed:
            try:
                from fastembed import TextEmbedding  # type: ignore

                # fails fast (no network attempt at request time) if model
                # files are absent from the local cache
                _model = TextEmbedding(model_name=_MODEL)
            except Exception:
                _model_failed = True
                return False
    return _model is not None


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Return 384-dim embeddings, or None when on the TF-IDF path."""
    if not texts:
        return []
    if not _fastembed_available():
        return None
    vectors = [v.tolist() for v in _model.embed(texts)]
    return vectors


def embed_one(text: str) -> list[float] | None:
    result = embed_texts([text])
    return result[0] if result else None


def vec_literal(vector: list[float]) -> str:
    """Format a vector as a pgvector literal."""
    return "[" + ",".join(f"{x:.7f}" for x in vector) + "]"


def parse_vector(value) -> list[float] | None:
    """Parse a pgvector column value (string '[a,b,c]' without the python
    adapter installed, or already-decoded list) into a list of floats."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [float(x) for x in value]
    text = str(value).strip().strip("[]")
    if not text:
        return None
    return [float(x) for x in text.split(",")]


class SkillTfidfIndex:
    """TF-IDF index over skill label+aliases for the fallback pipeline."""

    def __init__(self, skill_texts: list[str]):
        self.index = TfidfIndex(skill_texts)

    def score_pairs(self, a_text: str, b_text: str) -> float:
        return TfidfIndex.cosine(self.index.transform(a_text), self.index.transform(b_text))
