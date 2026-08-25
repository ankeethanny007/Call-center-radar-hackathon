"""Operational commands for reproducible ingestion, processing, and retry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import settings
from .database import SessionLocal
from .migrations import upgrade_database
from .pipeline import ingest_dataset, ingest_manifest, process_batch, validate_call
from .models import Call
from .storage import storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Call-Centre Radar offline processing")
    parser.add_argument(
        "command",
        choices=("init-db", "ingest-manifest", "ingest-dataset", "validate", "process", "retry", "reanalyse", "sync-storage"),
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--media-root", type=Path, default=settings.media_root)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    upgrade_database()
    if args.command == "init-db":
        print(json.dumps({"ok": True}))
        return
    db = SessionLocal()
    try:
        if args.command == "ingest-manifest":
            if not args.manifest: parser.error("--manifest is required")
            print(json.dumps({"imported": ingest_manifest(db, args.manifest)}))
        elif args.command == "ingest-dataset":
            if not args.dataset_root: parser.error("--dataset-root is required")
            print(json.dumps(ingest_dataset(db, args.dataset_root, args.media_root)))
        elif args.command == "validate":
            query = db.query(Call).filter(Call.processing_status.in_(("DISCOVERED", "VALIDATED", "FAILED"))).order_by(Call.created_at)
            if args.limit: query = query.limit(args.limit)
            result = {"validated": 0, "failed": 0}
            for call in query.all():
                try:
                    validate_call(call, args.media_root)
                    result["validated"] += 1
                except Exception as exc:
                    call.processing_status, call.processing_error = "FAILED", str(exc)[:4000]
                    result["failed"] += 1
            db.commit()
            print(json.dumps(result))
        elif args.command == "sync-storage":
            uploaded = 0
            query = db.query(Call).order_by(Call.created_at)
            if args.limit: query = query.limit(args.limit)
            for call in query.all():
                storage.upload(call.audio_path, args.media_root / call.audio_path)
                uploaded += 1
            print(json.dumps({"uploaded": uploaded, "provider": settings.storage_provider}))
        elif args.command == "reanalyse":
            query = db.query(Call).filter(
                Call.processing_status == "READY",
                Call.transcript_segments.any(),
            ).order_by(Call.created_at)
            if args.limit:
                query = query.limit(args.limit)
            calls = query.all()
            call_ids = [call.id for call in calls]
            for call in calls:
                # Preserve transcript work; the normal process state machine will
                # pass directly to the evidence-first analysis stage.
                call.processing_status = "TRANSCRIBED"
                call.processing_error = None
                call.processed_at = None
            db.commit()
            result = process_batch(db, args.media_root, call_ids=call_ids)
            print(json.dumps({"queued_for_reanalysis": len(call_ids), **result}))
        else:
            print(json.dumps(process_batch(db, args.media_root, limit=args.limit, retry_failed=args.command == "retry")))
    finally:
        db.close()


if __name__ == "__main__":
    main()
