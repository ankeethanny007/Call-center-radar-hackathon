#!/usr/bin/env python3
"""Export a balanced human-review worksheet for the evidence/AI golden set."""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.migrations import upgrade_database  # noqa: E402
from app.models import Call  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "work" / "golden-set-review.csv")
    parser.add_argument("--size", type=int, default=25)
    args = parser.parse_args()
    upgrade_database()
    db = SessionLocal()
    try:
        ready = db.query(Call).filter_by(processing_status="READY").all()
        by_category: dict[str, list[Call]] = defaultdict(list)
        for call in sorted(ready, key=lambda row: row.analysis.attention_score if row.analysis else 0, reverse=True):
            by_category[(call.analysis.intent_category if call.analysis else None) or "unclassified"].append(call)
        selected: list[Call] = []
        while len(selected) < args.size and any(by_category.values()):
            for category in sorted(by_category):
                if by_category[category] and len(selected) < args.size:
                    selected.append(by_category[category].pop(0))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=(
                "call_id", "customer", "agent", "predicted_intent", "predicted_resolution", "attention_score",
                "summary", "review_intent", "review_resolution", "review_mood_shift", "review_evidence_correct",
                "review_summary_correct", "reviewer_notes",
            ))
            writer.writeheader()
            for call in selected:
                analysis = call.analysis
                writer.writerow({
                    "call_id": call.id, "customer": call.customer.name if call.customer else "", "agent": call.agent.name if call.agent else "",
                    "predicted_intent": analysis.intent_category if analysis else "", "predicted_resolution": analysis.resolution_status if analysis else "",
                    "attention_score": analysis.attention_score if analysis else "", "summary": analysis.summary if analysis else "",
                    "review_intent": "", "review_resolution": "", "review_mood_shift": "", "review_evidence_correct": "", "review_summary_correct": "", "reviewer_notes": "",
                })
        print(f"Exported {len(selected)} calls to {args.output}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
