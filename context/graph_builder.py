"""Neo4j graph building and embedding storage for code context."""

from context.graph_config import get_embedding_model


def build_graph(chunks, file_nodes, driver):
    """Build graph nodes and relationships in Neo4j."""
    with driver.session() as session:

        for file_node in file_nodes:
            session.run(
                "MERGE (f:File {path: $path, last_parsed_hash: $last_parsed_hash, chunks: $chunks})",
                path=file_node.path,
                last_parsed_hash=file_node.last_parsed_hash,
                chunks=file_node.chunks,
            )
        for chunk in chunks:
            session.run(
                "MERGE (n:Chunk {name: $name, code: $code, start_line: $start_line, end_line: $end_line})",
                name=chunk.name,
                code=chunk.code,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
            )

        for file_node in file_nodes:
            for chunk_name in file_node.chunks:
                session.run(
                    """MATCH (f:File {path: $path}), (c:Chunk {name: $chunk_name})
                    CREATE (f)-[:CONTAINS]->(c)""",
                    path=file_node.path,
                    chunk_name=chunk_name,
                )

        for file_node in file_nodes:
            for imports_from in file_node.imports_from or []:
                if not imports_from:
                    continue
                session.run(
                    """MATCH (a:File {path: $source}), (b:File) WHERE b.path ENDS WITH $target
                        CREATE (a)-[:IMPORTS_FROM]->(b)""",
                    source=file_node.path,
                    target=imports_from,
                )

        for chunk in chunks:
            for r in chunk.relationships:
                session.run(
                    """
                    MATCH (a:Chunk {name: $source}), (b:Chunk)
                    WHERE b.name ENDS WITH $target
                    CREATE (a)-[:RELATES {type: $rel_type}]->(b)
                    """,
                    source=chunk.name,
                    target=r.target,
                    rel_type=r.relat_type,
                )


def embd_and_store(chunks, driver):
    """Create vector index and store embeddings for chunks."""
    with driver.session() as session:
        session.run("""
            CREATE VECTOR INDEX chunk_embeddings IF NOT EXISTS
            FOR (n:Chunk) ON n.embedding
            OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}
        """)
    emb = get_embedding_model()
    for chunk in chunks:
        vec = emb.encode(chunk.code)
        with driver.session() as session:
            session.run(
                "MATCH (n:Chunk {name: $name}) SET n.embedding = $embedding",
                name=chunk.name,
                embedding=vec.tolist(),
            )
