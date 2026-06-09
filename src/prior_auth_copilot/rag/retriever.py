"""
src/prior_auth_copilot/rag/retriever.py

PolicyRetriever — wraps the LanceDB policy store with a clean interface
for the Medical Necessity Reasoner node.

Usage:
    retriever = PolicyRetriever()
    chunks = retriever.retrieve("physical therapy lumbar spine coverage", top_k=8)
    for c in chunks:
        print(c.text, c.chunk_hash, c.section)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(REPO_ROOT / ".env", override=False)

POLICY_STORE_DIR = REPO_ROOT / os.getenv("POLICY_STORE_DIR", "data/policy-store")
EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
DEFAULT_TOP_K = int(os.getenv("TOP_K_POLICY_CHUNKS", "8"))
TABLE_NAME = "policy_chunks"


@dataclass
class PolicyChunk:
    """One retrieved policy paragraph."""
    text: str
    policy_id: str
    section: str
    paragraph_idx: int
    source_file: str
    chunk_hash: str
    score: float = 0.0


class PolicyRetriever:
    """
    Semantic retriever over the LanceDB policy store.

    Lazy-initialised — the LanceDB connection is opened on first call to
    retrieve() so import does not fail if the store hasn't been built yet.
    """

    def __init__(self) -> None:
        self._table = None
        self._embedder = None

    def _init(self) -> None:
        if self._table is not None:
            return

        try:
            import lancedb
            from langchain_openai import OpenAIEmbeddings
        except ImportError as exc:
            raise RuntimeError(
                f"Missing dependency: {exc}. Run: pip install lancedb langchain-openai"
            ) from exc

        if not POLICY_STORE_DIR.exists():
            raise RuntimeError(
                f"Policy store not found at {POLICY_STORE_DIR}. "
                "Run `make ingest-policies` first."
            )

        db = lancedb.connect(str(POLICY_STORE_DIR))
        if TABLE_NAME not in db.table_names():
            raise RuntimeError(
                f"Table '{TABLE_NAME}' not found in LanceDB store. "
                "Run `make ingest-policies` first."
            )

        self._table = db.open_table(TABLE_NAME)
        self._embedder = OpenAIEmbeddings(model=EMBED_MODEL)

    def retrieve(self, query: str, top_k: int = DEFAULT_TOP_K) -> list[PolicyChunk]:
        """
        Retrieve the top-k most semantically similar policy chunks for a query.

        Parameters
        ----------
        query  : natural-language query, e.g. "physical therapy requirement for lumbar MRI"
        top_k  : number of chunks to return (default: TOP_K_POLICY_CHUNKS env var)

        Returns
        -------
        List of PolicyChunk sorted by descending similarity score.
        """
        self._init()

        query_vector = self._embedder.embed_query(query)
        results = (
            self._table
            .search(query_vector)
            .limit(top_k)
            .to_list()
        )

        chunks: list[PolicyChunk] = []
        for row in results:
            chunks.append(PolicyChunk(
                text=row["text"],
                policy_id=row["policy_id"],
                section=row["section"],
                paragraph_idx=row["paragraph_idx"],
                source_file=row["source_file"],
                chunk_hash=row["chunk_hash"],
                score=float(row.get("_distance", 0.0)),
            ))

        return chunks

    def get_by_hash(self, chunk_hash: str) -> PolicyChunk | None:
        """
        Look up a policy chunk by its SHA-256 hash.
        Used by the citation checker to verify Reasoner citations.
        """
        self._init()
        results = (
            self._table
            .search()
            .where(f"chunk_hash = '{chunk_hash}'")
            .limit(1)
            .to_list()
        )
        if not results:
            return None
        row = results[0]
        return PolicyChunk(
            text=row["text"],
            policy_id=row["policy_id"],
            section=row["section"],
            paragraph_idx=row["paragraph_idx"],
            source_file=row["source_file"],
            chunk_hash=row["chunk_hash"],
        )

    def verify_citation(self, chunk_hash: str) -> bool:
        """Return True if chunk_hash exists in the policy store."""
        return self.get_by_hash(chunk_hash) is not None
