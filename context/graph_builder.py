"""Neo4j graph building and embedding storage for code context."""

from context.graph_config import get_embedding_model
from context.graph_config import embed


def build_graph(chunks, file_nodes, driver):
    """Build graph nodes and relationships in Neo4j."""
    with driver.session() as session:
        # OLD: Sequential File node creation (kept for reference)
        # for file_node in file_nodes:
        #     session.run(
        #         "MERGE (f:File {path: $path, last_parsed_hash: $last_parsed_hash, chunks: $chunks})",
        #         path=file_node.path,
        #         last_parsed_hash=file_node.last_parsed_hash,
        #         chunks=file_node.chunks,
        #     )
        # for chunk in chunks:
        #     session.run(
        #         "MERGE (n:Chunk {name: $name, code: $code, start_line: $start_line, end_line: $end_line})",
        #         name=chunk.name,
        #         code=chunk.code,
        #         start_line=chunk.start_line,
        #         end_line=chunk.end_line,
        #     )

        # NEW: Batch File and Chunk node creation
        session.run(
            """
            UNWIND $files AS file
            MERGE (f:File {path: file.path})
            SET f.last_parsed_hash = file.last_parsed_hash, f.chunks = file.chunks
            """,
            files=[
                {
                    "path": fn.path,
                    "last_parsed_hash": fn.last_parsed_hash,
                    "chunks": fn.chunks,
                }
                for fn in file_nodes
            ],
        )
        session.run(
            """
            UNWIND $chunks AS chunk
            MERGE (n:Chunk {name: chunk.name})
            SET n.code = chunk.code, n.start_line = chunk.start_line, n.end_line = chunk.end_line
            """,
            chunks=[
                {
                    "name": c.name,
                    "code": c.code,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                }
                for c in chunks
            ],
        )

        # OLD: Sequential CONTAINS relationship creation (kept for reference)
        # for file_node in file_nodes:
        #     for chunk_name in file_node.chunks:
        #         session.run(
        #             """MATCH (f:File {path: $path}), (c:Chunk {name: $chunk_name})
        #             CREATE (f)-[:CONTAINS]->(c)""",
        #             path=file_node.path,
        #             chunk_name=chunk_name,
        #         )

        # NEW: Batch CONTAINS relationship creation
        contains_data = []
        for file_node in file_nodes:
            for chunk_name in file_node.chunks:
                contains_data.append({"path": file_node.path, "chunk_name": chunk_name})
        if contains_data:
            session.run(
                """
                UNWIND $data AS item
                MATCH (f:File {path: item.path})
                MATCH (c:Chunk {name: item.chunk_name})
                CREATE (f)-[:CONTAINS]->(c)
                """,
                data=contains_data,
            )

        # OLD: Cartesian product for IMPORTS_FROM (kept for reference)
        # for file_node in file_nodes:
        #     for imports_from in file_node.imports_from or []:
        #         if not imports_from:
        #             continue
        #         session.run(
        #             """MATCH (a:File {path: $source}), (b:File) WHERE b.path ENDS WITH $target LIMIT 1
        #                 CREATE (a)-[:IMPORTS_FROM]->(b)""",
        #             source=file_node.path,
        #             target=imports_from,
        #         )

        # NEW: Build file path map first to avoid cartesian product
        file_path_map = {fn.path: fn for fn in file_nodes}

        for file_node in file_nodes:
            for imports_from in file_node.imports_from or []:
                if not imports_from:
                    continue
                # Find target file using map lookup
                target_path = None
                for fp in file_path_map:
                    if fp.endswith(imports_from) or fp == imports_from:
                        target_path = fp
                        break
                if target_path:
                    session.run(
                        """
                        MATCH (a:File {path: $source})
                        MATCH (b:File {path: $target})
                        CREATE (a)-[:IMPORTS_FROM]->(b)""",
                        source=file_node.path,
                        target=target_path,
                    )

        # OLD: Cartesian product approach (kept for reference)
        # This was slow because MATCH (a), (b) creates all combinations
        # for chunk in chunks:
        #     for r in chunk.relationships:
        #         session.run(
        #             """
        #             MATCH (a:Chunk {name: $source}), (b:Chunk)
        #             WHERE b.name ENDS WITH $target LIMIT 1
        #             CREATE (a)-[:RELATES {type: $rel_type}]->(b)
        #             """,
        #             source=chunk.name,
        #             target=r.target,
        #             rel_type=r.relat_type,
        #         )

        # NEW: Build lookup map first, then direct MATCH to avoid cartesian product
        chunk_map = {chunk.name: chunk for chunk in chunks}

        for chunk in chunks:
            for r in chunk.relationships:
                # Find target chunk name using map lookup instead of WHERE clause
                target_name = None
                for cn in chunk_map:
                    if cn.endswith(r.target):
                        target_name = cn
                        break
                if target_name:
                    session.run(
                        """
                        MATCH (a:Chunk {name: $source})
                        MATCH (b:Chunk {name: $target})
                        CREATE (a)-[:RELATES {type: $rel_type}]->(b)
                        """,
                        source=chunk.name,
                        target=target_name,
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

    # OLD: Sequential embedding approach (kept for reference)
    # for chunk in chunks:
    #     vec = embed(chunk.code)
    #     with driver.session() as session:
    #         session.run(
    #             "MATCH (n:Chunk {name: $name}) SET n.embedding = $embedding",
    #             name=chunk.name,
    #             embedding=vec.tolist(),
    #         )

    # NEW: Batch embedding + batch Neo4j write for much faster processing
    all_codes = [chunk.code for chunk in chunks]
    embeddings = embed(all_codes)  # Single batch call to local model

    with driver.session() as session:
        session.run(
            """
            UNWIND $data AS item
            MATCH (n:Chunk {name: item.name})
            SET n.embedding = item.embedding
        """,
            data=[
                {"name": c.name, "embedding": e.tolist()}
                for c, e in zip(chunks, embeddings)
            ],
        )
