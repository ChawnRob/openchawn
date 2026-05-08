"""
Embedding provider local-first (V11.6).

- Priorité: sentence-transformers local (si disponible).
- Fallback: hash embedding déterministe, mockable pour les tests.
- Aucun appel réseau, aucun LLM.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

_MODEL = None
_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_HASH_DIM = 256

_TOKEN_CANON = {
    "explain": "explain",
    "explique": "explain",
    "expliquer": "explain",
    "explica": "explain",
    "explicar": "explain",
    "traduis": "translate",
    "translate": "translate",
    "traduire": "translate",
    "memory": "memory",
    "memoire": "memory",
    "mémoire": "memory",
    "railway": "railway",
    "deepseek": "deepseek",
    "openchawn": "openchawn",
    "deploy": "deploy",
    "deployment": "deploy",
    "déploiement": "deploy",
    "deploiement": "deploy",
    "production": "production",
    "prod": "production",
    "comment": "how",
    "how": "how",
    "avec": "with",
    "with": "with",
    "english": "english",
    "anglais": "english",
    "french": "french",
    "français": "french",
    "francais": "french",
}


def _normalize_tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-zA-Z0-9àâäéèêëïîôùûçñáíóúü]+", (text or "").lower())
    out: list[str] = []
    for t in raw:
        out.append(_TOKEN_CANON.get(t, t))
    return out


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 1e-12:
        return vec
    return [v / norm for v in vec]


def _hash_embedding(text: str, dim: int = _HASH_DIM) -> list[float]:
    tokens = _normalize_tokens(text)
    if not tokens:
        return [0.0] * dim
    vec = [0.0] * dim
    for tok in tokens:
        h = hashlib.sha256(tok.encode("utf-8")).digest()
        for i in range(0, min(dim, 32)):
            vec[i] += (h[i] / 255.0) - 0.5
        if dim > 32:
            h2 = hashlib.md5(tok.encode("utf-8")).digest()
            for i in range(32, min(dim, 48)):
                vec[i] += (h2[i - 32] / 255.0) - 0.5
    return _l2_normalize(vec)


def _get_sentence_transformer():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        _MODEL = SentenceTransformer(_MODEL_NAME)
    except Exception:
        _MODEL = False
    return _MODEL


def embed_text(text: str) -> dict[str, Any]:
    model = _get_sentence_transformer()
    raw = (text or "").strip()
    if not raw:
        return {"status": "ok", "provider": "hash_fallback", "vector": [0.0] * _HASH_DIM, "dimension": _HASH_DIM}
    if model and model is not False:
        try:
            vec = model.encode(raw, normalize_embeddings=True)
            out = [float(x) for x in vec.tolist()]
            return {
                "status": "ok",
                "provider": "sentence_transformers_local",
                "vector": out,
                "dimension": len(out),
            }
        except Exception:
            pass
    hv = _hash_embedding(raw, _HASH_DIM)
    return {"status": "ok", "provider": "hash_fallback", "vector": hv, "dimension": len(hv)}


def embed_batch(texts: list[str]) -> dict[str, Any]:
    arr = list(texts or [])
    if not arr:
        return {"status": "ok", "provider": "hash_fallback", "vectors": [], "dimension": _HASH_DIM}

    model = _get_sentence_transformer()
    if model and model is not False:
        try:
            vecs = model.encode(arr, normalize_embeddings=True)
            out = [[float(x) for x in row.tolist()] for row in vecs]
            dim = len(out[0]) if out else 0
            return {"status": "ok", "provider": "sentence_transformers_local", "vectors": out, "dimension": dim}
        except Exception:
            pass

    out = [_hash_embedding(x, _HASH_DIM) for x in arr]
    return {"status": "ok", "provider": "hash_fallback", "vectors": out, "dimension": _HASH_DIM}

