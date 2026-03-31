"""Vector similarity search and graph-based context retrieval."""

import numpy as np

from core.config import GRAPH_RETRIEVAL_MAX_CHARS, GRAPH_RETRIEVAL_MAX_TOKENS
from context.graph_config import embed
from core.token_usage import estimate_tokens


def similarity_search(query, driver, k=5):
    """Search for similar chunks using vector embeddings.

    Falls back to manual computation if vector index fails.
    """
    query_vec = embed(query)
    # Ensure 1D array
    if query_vec.ndim > 1:
        query_vec = query_vec[0]

    try:
        with driver.session() as session:
            results = session.run(
                """
                CALL db.index.vector.queryNodes('chunk_embeddings', $k, $embedding)
                YIELD node, score
                RETURN node.name AS name, score AS score
                """,
                k=k,
                embedding=query_vec.tolist(),
            )
            ordered = []
            for row in results:
                name = row.get("name")
                if not name:
                    continue
                ordered.append((name, row.get("score", 0.0)))
            return ordered
    except Exception as e:
        # Fallback: manual similarity computation
        return _manual_similarity_search(query_vec, driver, k)


def _manual_similarity_search(query_vec, driver, k=5):
    """Fallback similarity search using manual cosine similarity."""
    with driver.session() as session:
        result = session.run("""
            MATCH (c:Chunk)
            WHERE c.embedding IS NOT NULL
            RETURN c.name as name, c.embedding as embedding
        """)

        similarities = []
        for r in result:
            emb = np.array(r["embedding"])
            # Handle both 1D and 2D arrays
            if emb.ndim > 1:
                emb = emb[0]
            # Cosine similarity
            sim = np.dot(query_vec, emb) / (
                np.linalg.norm(query_vec) * np.linalg.norm(emb)
            )
            similarities.append((r["name"], sim))

        # Sort by similarity and return top k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:k]


def get_context(top_k_chunks, driver):
    """Expand context by following graph relationships."""
    base_names = [name for name, _score in top_k_chunks]
    context = set(base_names)
    with driver.session() as session:
        for chunk_name in base_names:
            results = session.run(
                "MATCH (a:Chunk {name: $name})-[:RELATES]->(b) RETURN b.name AS name",
                name=chunk_name,
            )
            for res in results:
                if res["name"]:
                    context.add(res["name"])
    return list(context)


def retrieve_code_context(
    query: str,
    driver,
    k: int = 5,
    max_chars: int = GRAPH_RETRIEVAL_MAX_CHARS,
    max_tokens: int = GRAPH_RETRIEVAL_MAX_TOKENS,
) -> str:
    """Vector search + graph expansion with budget-aware, deduped context."""
    top_chunks = similarity_search(query, driver, k=k)
    if not top_chunks:
        return "No matching chunks in the graph index."

    top_names = [name for name, _score in top_chunks]
    expanded = get_context(top_chunks, driver)
    context_nodes = top_names + [n for n in expanded if n not in set(top_names)]

    context_code = []
    used_tokens = 0
    seen_names = set()
    seen_code_fingerprints = set()
    trimmed = False

    with driver.session() as session:
        for node in context_nodes:
            if node in seen_names:
                continue
            seen_names.add(node)
            result = session.run(
                "MATCH (n:Chunk {name: $name}) RETURN n.name AS name, n.code AS code",
                name=node,
            )
            for r in result:
                code = r.get("code") or ""
                if not code:
                    continue
                fingerprint = hash(code.strip())
                if fingerprint in seen_code_fingerprints:
                    continue
                seen_code_fingerprints.add(fingerprint)

                block = f"--- Chunk: {r['name']} ---\n{code}"
                block_tokens = estimate_tokens(block)

                if used_tokens + block_tokens > max_tokens:
                    trimmed = True
                    continue

                context_code.append(block)
                used_tokens += block_tokens

    text = "\n\n".join(context_code)
    if trimmed:
        text += "\n\n[...truncated context due to token budget...]"
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...truncated context...]"
    return text
