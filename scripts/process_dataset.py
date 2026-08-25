#!/usr/bin/env python3
"""One-command local dataset ingestion and resumable processing.

Usage (from repository root):
  python scripts/process_dataset.py --input data/callradar-data --limit 10
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.migrations import upgrade_database  # noqa: E402
from app.pipeline import ingest_dataset, process_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "callradar-data")
    parser.add_argument("--media-root", type=Path, default=ROOT / "data")
    parser.add_argument("--limit", type=int, help="Process at most this many calls")
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    upgrade_database()
    db = SessionLocal()
    try:
        print("Ingest:", ingest_dataset(db, args.input, args.media_root))
        print("Process:", process_batch(db, args.media_root, args.limit, args.retry_failed))
    finally:
        db.close()


if __name__ == "__main__":
    main()
