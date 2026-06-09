"""
src/prior_auth_copilot/rag/ingest.py

Policy corpus ingestion pipeline — chunks policy markdown files and stores
paragraph-level embeddings in a LanceDB table.

Usage:
    python scripts/ingest_policies.py          # ingest all policies in data/policies/
    make ingest-policies                        # same via Makefile

The LanceDB store is written to POLICY_STORE_DIR (default: data/policy-store/).
It is gitignored and must be rebuilt on a fresh checkout before the Reasoner
can run.  Ingestion is idempotent — re-running drops and recreates the table.

Schema (per chunk / row in LanceDB)
------------------------------------
  text          : str   — raw paragraph text
  vector        : list  — embedding (text-embedding-3-small, 1536 dims)
  policy_id     : str   — e.g. "cms-ncd-220.6.17"
  section       : str   — e.g. "Section A — Indications: Covered Conditions"
  paragraph_idx : int   — 0-based paragraph index within the section
  source_file   : str   — relative path to the source policy file
  chunk_hash    : str   — sha256 of the text (used by the citation checker)
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(REPO_ROOT / ".env", override=False)

POLICIES_DIR = REPO_ROOT / "data/policies"
POLICY_STORE_DIR = REPO_ROOT / os.getenv("POLICY_STORE_DIR", "data/policy-store")
EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
TABLE_NAME = "policy_chunks"


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _parse_policy_file(path: Path) -> list[dict]:
    """
    Parse a policy markdown file into paragraph-level chunks.

    Sections are delimited by lines starting with "## ".
    Within each section, chunks are separated by blank lines.
    Comment lines (starting with #, not ##) and the front-matter block are skipped.
    """
    # Extract policy_id from front-matter comment: "# policy_id: ..."
    content = path.read_text(encoding="utf-8")
    policy_id = path.stem  # fallback
    for line in content.splitlines():
        if line.startswith("# policy_id:"):
            policy_id = line.split(":", 1)[1].strip()
            break

    chunks: list[dict] = []
    current_section = "Preamble"
    current_paragraphs: list[str] = []

    def _flush(section: str, paras: list[str]) -> None:
        for idx, para in enumerate(paras):
            text = para.strip()
            if not text:
                continue
            chunks.append({
                "text": text,
                "policy_id": policy_id,
                "section": section,
                "paragraph_idx": idx,
                "source_file": str(path.relative_to(REPO_ROOT)),
                "chunk_hash": hashlib.sha256(text.encode()).hexdigest(),
            })

    paragraph_buffer: list[str] = []

    for line in content.splitlines():
        # Skip front-matter comment lines
        if re.match(r"^#(?!#)", line):
            continue
        if line.startswith("## "):
            # Flush current paragraph buffer into current section
            if paragraph_buffer:
                current_paragraphs.append(" ".join(paragraph_buffer))
                paragraph_buffer = []
            _flush(current_section, current_paragraphs)
            current_section = line[3:].strip()
            current_paragraphs = []
        elif line.strip() == "":
            if paragraph_buffer:
                current_paragraphs.append(" ".join(paragraph_buffer))
                paragraph_buffer = []
        else:
            paragraph_buffer.append(line.strip())

    if paragraph_buffer:
        current_paragraphs.append(" ".join(paragraph_buffer))
    _flush(current_section, current_paragraphs)

    return chunks


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


def ingest_all(verbose: bool = True) -> int:
    """
    Ingest all policy files from POLICIES_DIR into LanceDB.
    Drops and recreates the table on each run (idempotent).
    Returns total number of chunks stored.
    """
    try:
        import lancedb
        from langchain_openai import OpenAIEmbeddings
    except ImportError as exc:
        print(f"ERROR: missing dependency — {exc}")
        print("Run: pip install lancedb langchain-openai")
        sys.exit(1)

    policy_files = sorted(POLICIES_DIR.glob("*.md"))
    if not policy_files:
        print(f"ERROR: No policy files found in {POLICIES_DIR}")
        sys.exit(1)

    if verbose:
        print(f"Embedding model : {EMBED_MODEL}")
        print(f"Policy store    : {POLICY_STORE_DIR}")
        print(f"Policy files    : {[f.name for f in policy_files]}\n")

    # Collect all chunks
    all_chunks: list[dict] = []
    for pf in policy_files:
        chunks = _parse_policy_file(pf)
        if verbose:
            print(f"  {pf.name}: {len(chunks)} chunks")
        all_chunks.extend(chunks)

    if verbose:
        print(f"\nTotal chunks to embed: {len(all_chunks)}")

    # Embed all texts in one batch
    embedder = OpenAIEmbeddings(model=EMBED_MODEL)
    texts = [c["text"] for c in all_chunks]
    if verbose:
        print("Embedding ...", end=" ", flush=True)
    vectors = embedder.embed_documents(texts)
    if verbose:
        print(f"done ({len(vectors)} vectors, dim={len(vectors[0])})")

    # Build LanceDB rows
    rows = []
    for chunk, vector in zip(all_chunks, vectors):
        rows.append({**chunk, "vector": vector})

    # Write to LanceDB (drop + recreate for idempotency)
    POLICY_STORE_DIR.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(POLICY_STORE_DIR))

    if TABLE_NAME in db.table_names():
        db.drop_table(TABLE_NAME)
        if verbose:
            print(f"Dropped existing table '{TABLE_NAME}'")

    table = db.create_table(TABLE_NAME, data=rows)
    if verbose:
        print(f"Created table '{TABLE_NAME}' with {len(rows)} rows")
        print(f"\nPolicy store ready → {POLICY_STORE_DIR}")

    return len(rows)


if __name__ == "__main__":
    ingest_all()
