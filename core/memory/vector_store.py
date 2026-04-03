"""
FAISS-backed vector store for semantic memory retrieval.
Persists to .code-m8/memory_vectors/ across sessions.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

import numpy as np

try:
    from context.graph_config import embed
except ImportError:
    embed = None

try:
    from utils.logger import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

_STORE_DIR = Path(".code-m8/memory_vectors")
_META_DB = _STORE_DIR / "meta.db"

_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    key      TEXT UNIQUE NOT NULL,
    text     TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);
"""

try:
    import faiss

    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("faiss-cpu not installed — falling back to numpy cosine search")


class VectorStore:
    """
    Disk-persistent FAISS vector store.
    Falls back to numpy cosine search if faiss not installed.
    """

    DIM = 384  # all-MiniLM-L6-v2

    def __init__(self):
        _STORE_DIR.mkdir(parents=True, exist_ok=True)
        self._index = None  # faiss.IndexFlatIP or None
        self._keys: list[str] = []
        self._meta: dict[str, dict] = {}
        self._embeddings: list[np.ndarray] = []
        self._dirty = False
        self._load()

    # ── public API ────────────────────────────────────────────────────────────

    def upsert(self, key: str, text: str, metadata: dict | None = None) -> None:
        if embed is None:
            logger.warning("VectorStore: embed function not available")
            return

        emb = embed(text)
        if emb.ndim > 1:
            emb = emb[0]
        vec = emb / (np.linalg.norm(emb) + 1e-8)

        if key in self._meta:
            idx = self._keys.index(key)
            self._embeddings[idx] = vec
        else:
            self._keys.append(key)
            self._embeddings.append(vec)
            self._meta[key] = {"text": text, **(metadata or {})}

        self._save_meta(key, text, metadata or {})
        self._dirty = True
        if len(self._keys) % 20 == 0:
            self._rebuild_faiss()

    def search(self, query: str, top_k: int = 6) -> list[dict]:
        """Returns list of {key, text, score, metadata}"""
        if not self._keys or embed is None:
            return []
        qvec = embed(query)
        if qvec.ndim > 1:
            qvec = qvec[0]
        qvec = qvec / (np.linalg.norm(qvec) + 1e-8)
        return self._cosine_search(qvec, top_k)

    def mmr_search(
        self, query: str, top_k: int = 6, diversity: float = 0.5
    ) -> list[dict]:
        """
        Maximal Marginal Relevance — balances relevance + diversity.
        """
        candidates = self.search(query, top_k=top_k * 3)
        if len(candidates) <= top_k:
            return candidates

        selected: list[dict] = []
        candidate_embs = [self._get_emb(c["key"]) for c in candidates]

        selected.append(candidates[0])
        remaining = list(range(1, len(candidates)))

        while len(selected) < top_k and remaining:
            best_idx = -1
            best_score = -1e9
            sel_embs = [self._get_emb(s["key"]) for s in selected]

            for ri in remaining:
                relevance = candidates[ri]["score"]
                redundancy = max(
                    float(np.dot(candidate_embs[ri], se)) for se in sel_embs
                )
                score = (1 - diversity) * relevance - diversity * redundancy
                if score > best_score:
                    best_score = score
                    best_idx = ri

            selected.append(candidates[best_idx])
            remaining.remove(best_idx)

        return selected

    def delete(self, key_prefix: str) -> int:
        """Delete all entries whose key starts with key_prefix."""
        to_remove = [k for k in self._keys if k.startswith(key_prefix)]
        for k in to_remove:
            idx = self._keys.index(k)
            self._keys.pop(idx)
            self._embeddings.pop(idx)
            self._meta.pop(k, None)
        if to_remove:
            with self._meta_conn() as c:
                c.executemany(
                    "DELETE FROM chunks WHERE key=?", [(k,) for k in to_remove]
                )
            self._rebuild_faiss()
        return len(to_remove)

    def count(self) -> int:
        return len(self._keys)

    # ── private ───────────────────────────────────────────────────────────────

    def _cosine_search(self, qvec: np.ndarray, top_k: int) -> list[dict]:
        if FAISS_AVAILABLE and self._index is not None and self._embeddings:
            matrix = np.array(self._embeddings, dtype="float32")
            q = qvec.reshape(1, -1).astype("float32")
            scores, indices = self._index.search(q, min(top_k, len(self._keys)))
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self._keys):
                    continue
                key = self._keys[idx]
                meta = self._meta.get(key, {})
                results.append(
                    {
                        "key": key,
                        "text": meta.get("text", ""),
                        "score": float(score),
                        "metadata": meta,
                    }
                )
            return results
        else:
            # numpy fallback
            if not self._embeddings:
                return []
            emb_matrix = np.array(self._embeddings)
            scores = emb_matrix @ qvec
            indices = np.argsort(scores)[::-1][:top_k]
            results = []
            for idx in indices:
                if idx >= len(self._keys):
                    continue
                key = self._keys[idx]
                meta = self._meta.get(key, {})
                results.append(
                    {
                        "key": key,
                        "text": meta.get("text", ""),
                        "score": float(scores[idx]),
                        "metadata": meta,
                    }
                )
            return results

    def _get_emb(self, key: str) -> np.ndarray:
        idx = self._keys.index(key)
        return self._embeddings[idx]

    def _rebuild_faiss(self) -> None:
        if not FAISS_AVAILABLE or not self._embeddings:
            return
        matrix = np.array(self._embeddings, dtype="float32")
        index = faiss.IndexFlatIP(self.DIM)
        index.add(matrix)
        self._index = index

    def _load(self) -> None:
        """Load index + metadata from disk."""
        try:
            with self._meta_conn() as c:
                rows = c.execute("SELECT key, text, metadata FROM chunks").fetchall()
            for row in rows:
                meta = json.loads(row["metadata"] or "{}")
                meta["text"] = row["text"]
                self._meta[row["key"]] = meta
                self._keys.append(row["key"])
        except Exception as e:
            logger.debug(f"VectorStore: no metadata to load ({e})")

        if self._keys and embed is not None:
            texts = [self._meta[k]["text"] for k in self._keys]
            try:
                embs = embed(texts)
                if embs.ndim == 1:
                    embs = embs.reshape(1, -1)
                self._embeddings = list(
                    emb / (np.linalg.norm(emb) + 1e-8) for emb in embs
                )
                self._rebuild_faiss()
            except Exception as e:
                logger.warning(f"VectorStore: embedding load failed: {e}")
                self._embeddings = [np.zeros(self.DIM) for _ in self._keys]

    def _save_meta(self, key: str, text: str, metadata: dict) -> None:
        with self._meta_conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO chunks(key, text, metadata) VALUES(?,?,?)",
                (key, text, json.dumps(metadata)),
            )

    def _meta_conn(self) -> sqlite3.Connection:
        _STORE_DIR.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(_META_DB)
        c.executescript(_META_SCHEMA)
        c.row_factory = sqlite3.Row
        return c


_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
