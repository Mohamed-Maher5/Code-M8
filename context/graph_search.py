"""Vector similarity search and graph-based context retrieval."""

from context.graph_config import get_embedding_model


def similarity_search(query, driver, k=5):
    """Search for similar chunks using vector embeddings."""
    query_vec = get_embedding_model().encode(query)
    with driver.session() as session:
        results = session.run(
            """
            CALL db.index.vector.queryNodes('chunk_embeddings', $k, $embedding)
            YIELD node, score
            RETURN node.name AS name
            """,
            k=k,
            embedding=query_vec.tolist(),
        )
        return [r["name"] for r in results if r.get("name")]


def get_context(top_k_chunks, driver):
    """Expand context by following graph relationships."""
    context = set(top_k_chunks)
    with driver.session() as session:
        for chunk_name in top_k_chunks:
            results = session.run(
                "MATCH (a:Chunk {name: $name})-[:RELATES]->(b) RETURN b.name AS name",
                name=chunk_name,
            )
            for res in results:
                if res["name"]:
                    context.add(res["name"])
    return list(context)


def retrieve_code_context(query: str, driver, k: int = 5, max_chars: int = 24000) -> str:
    """Vector search + graph expansion; returns concatenated code with chunk headers."""
    top_chunks = similarity_search(query, driver, k=k)
    if not top_chunks:
        return "No matching chunks in the graph index."

    context_nodes = get_context(top_chunks, driver)
    context_code = []
    with driver.session() as session:
        for node in context_nodes:
            result = session.run(
                "MATCH (n:Chunk {name: $name}) RETURN n.name AS name, n.code AS code",
                name=node,
            )
            for r in result:
                context_code.append(f"--- Chunk: {r['name']} ---\n{r['code']}")

    text = "\n\n".join(context_code)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...truncated context...]"
    return text
