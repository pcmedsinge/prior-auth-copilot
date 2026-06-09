#!/usr/bin/env python3
"""
scripts/ingest_policies.py — run the policy corpus ingestion pipeline.

Usage:
    python scripts/ingest_policies.py
    make ingest-policies
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from prior_auth_copilot.rag.ingest import ingest_all

if __name__ == "__main__":
    print("Prior-Auth Co-pilot — Policy Corpus Ingestion\n")
    total = ingest_all(verbose=True)
    print(f"\nIngestion complete — {total} chunks stored.")
