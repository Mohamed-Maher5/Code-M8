"""Graph RAG configuration — Neo4j + lazy-loaded embedding model."""

import os

import tiktoken
from dotenv import load_dotenv

load_dotenv()

enc = tiktoken.get_encoding("cl100k_base")

_embedding_model = None
_neo4j_driver = None

NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


def graph_rag_enabled() -> bool:
    return bool(NEO4J_URI and NEO4J_USERNAME and NEO4J_PASSWORD)


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


def get_driver():
    """Singleton Neo4j driver; None if graph RAG is not configured."""
    global _neo4j_driver
    if not graph_rag_enabled():
        return None
    if _neo4j_driver is None:
        from neo4j import GraphDatabase

        _neo4j_driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
            max_connection_lifetime=3600,
            keep_alive=True,
        )
    return _neo4j_driver


def close_driver() -> None:
    global _neo4j_driver
    if _neo4j_driver is not None:
        _neo4j_driver.close()
        _neo4j_driver = None
