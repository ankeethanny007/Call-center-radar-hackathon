#!/usr/bin/env python3
"""Retry only failed Call-Centre Radar records; completed calls are never reprocessed."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.migrations import upgrade_database  # noqa: E402
from app.pipeline import process_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--media-root", type=Path, default=ROOT / "data")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    upgrade_database()
    db = SessionLocal()
    try:
        print(process_batch(db, args.media_root, limit=args.limit, retry_failed=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
