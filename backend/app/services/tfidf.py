"""Pure-Python TF-IDF (no numpy/sklearn dependency).

Used as the deterministic rule-based fallback when local embedding models are
unavailable, so the matching pipeline never calls a network at request time.
"""
import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#./-]*")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "in", "into", "is", "it", "its", "of", "on", "or", "our",
    "that", "the", "their", "them", "there", "this", "to", "was", "we", "were",
    "will", "with", "you", "your", "also", "using", "used", "use", "work",
    "working", "experience", "skills", "strong", "good", "must", "should",
    "can", "who", "what", "etc", "plus", "like", "across", "per", "over",
}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


def literal_token_overlap(text_a: str, text_b: str) -> float:
    """Jaccard overlap of raw keyword sets — reported in match payloads so the
    demo can PROVE a high semantic score exists even when this number is 0."""
    a = set(t for t in _TOKEN_RE.findall(text_a.lower()) if t not in STOPWORDS)
    b = set(t for t in _TOKEN_RE.findall(text_b.lower()) if t not in STOPWORDS)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class TfidfIndex:
    """TfidfVectorizer equivalent over a fixed corpus of documents."""

    def __init__(self, documents: list[str]):
        self.docs = [tokenize(d) for d in documents]
        df: Counter = Counter()
        for doc in self.docs:
            df.update(set(doc))
        self.n_docs = max(len(self.docs), 1)
        self.idf = {
            term: math.log((self.n_docs + 1) / (count + 1)) + 1.0
            for term, count in df.items()
        }
        self.vectors = [self._vector(doc) for doc in self.docs]

    def _vector(self, tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        return {t: (1.0 + math.log(c)) * self.idf.get(t, 1.0) for t, c in tf.items()}

    def transform(self, text: str) -> dict[str, float]:
        return self._vector(tokenize(text))

    @staticmethod
    def cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(v * b.get(t, 0.0) for t, v in a.items())
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)

    def top_matches(self, text: str, top_k: int = 10) -> list[tuple[int, float]]:
        q = self.transform(text)
        scored = [
            (i, TfidfIndex.cosine(q, v)) for i, v in enumerate(self.vectors)
        ]
        scored = [s for s in scored if s[1] > 0.02]
        scored.sort(key=lambda s: -s[1])
        return scored[:top_k]
