"""Graph RAG configuration — Neo4j + lazy-loaded embedding model."""

import json
import os
from pathlib import Path

import numpy as np
import tiktoken
from dotenv import load_dotenv

load_dotenv()

enc = tiktoken.get_encoding("cl100k_base")

_embedding_model = None
_neo4j_driver = None
_hf_client = None
_embedding_cache = {}
_model_info_cache = None

_CACHE_DIR = Path("./.embedding_cache")
_CACHE_FILE = _CACHE_DIR / "embeddings.json"

NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


def _load_persistent_cache():
    """Load embedding cache from disk."""
    global _embedding_cache
    if _CACHE_FILE.exists():
        try:
            data = json.loads(_CACHE_FILE.read_text())
            _embedding_cache = {k: np.array(v) for k, v in data.items()}
        except Exception:
            pass


def _save_persistent_cache():
    """Save embedding cache to disk."""
    try:
        _CACHE_DIR.mkdir(exist_ok=True)
        data = {k: v.tolist() for k, v in _embedding_cache.items()}
        _CACHE_FILE.write_text(json.dumps(data))
    except Exception:
        pass


_load_persistent_cache()


def graph_rag_enabled() -> bool:
    return bool(NEO4J_URI and NEO4J_USERNAME and NEO4J_PASSWORD)


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


def get_hf_client():
    global _hf_client
    if _hf_client is None:
        from huggingface_hub import InferenceClient

        api_key = os.environ.get("HF_TOKEN") or os.environ.get("HF_API_TOKEN")
        _hf_client = InferenceClient(
            provider="auto",
            api_key=api_key,
        )
    return _hf_client


def get_driver():
    """Singleton Neo4j driver; None if graph RAG is not configured."""
    global _neo4j_driver
    if not graph_rag_enabled():
        return None
    if _neo4j_driver is None:
        try:
            from neo4j import GraphDatabase
        except ImportError:
            return None

        try:
            _neo4j_driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
                max_connection_lifetime=3600,
                keep_alive=True,
            )
        except Exception:
            return None
    return _neo4j_driver


def close_driver() -> None:
    global _neo4j_driver
    if _neo4j_driver is not None:
        _neo4j_driver.close()
        _neo4j_driver = None


def embed(texts):
    """Generate embeddings for text or list of texts using HuggingFace API.

    Uses HuggingFace Inference API for embeddings with caching.
    Requires HF_TOKEN to be set in environment.
    """
    global _embedding_cache

    client = get_hf_client()
    model_name = "sentence-transformers/all-MiniLM-L6-v2"

    if isinstance(texts, str):
        texts = [texts]

    embeddings = []
    uncached_texts = []
    uncached_indices = []

    # Check cache first
    for i, text in enumerate(texts):
        if text in _embedding_cache:
            embeddings.append(_embedding_cache[text])
        else:
            uncached_texts.append(text)
            uncached_indices.append(i)
            embeddings.append(None)

    # Batch API call for uncached texts (single API call for all)
    if uncached_texts:
        results = client.feature_extraction(uncached_texts, model=model_name)
        for text, result in zip(uncached_texts, results):
            _embedding_cache[text] = np.array(result)
        _save_persistent_cache()

    # Fill in uncached results from cache
    for i, idx in enumerate(uncached_indices):
        embeddings[idx] = _embedding_cache[uncached_texts[i]]

    # Stack embeddings - for single item, use np.array then reshape to 2D
    # This ensures consistent (n, 384) shape for iteration
    stacked = np.stack(embeddings)
    if len(embeddings) == 1:
        return stacked.reshape(1, -1)  # Ensure (1, 384) not (384,)
    return stacked


def clear_embedding_cache():
    """Clear the embedding cache (both memory and disk)."""
    global _embedding_cache
    _embedding_cache = {}
    if _CACHE_FILE.exists():
        _CACHE_FILE.unlink()


# OLD: HuggingFace API approach (kept for reference)
# def embed_OLD(text):
#     client = get_hf_client()
#     return client.feature_extraction(
#         text, model="sentence-transformers/all-MiniLM-L6-v2"
#     )


def compute_sentence_similarity(
    source_sentence: str,
    sentences: list[str],
) -> list[float]:
    source_embedding = embed(source_sentence)
    sentences_embeddings = embed(sentences)

    source_emb = np.array(source_embedding)
    sents_embs = np.array(sentences_embeddings)

    similarities = np.dot(source_emb, sents_embs.T) / (
        np.linalg.norm(source_emb) * np.linalg.norm(sents_embs, axis=1)
    )
    return similarities.tolist()
