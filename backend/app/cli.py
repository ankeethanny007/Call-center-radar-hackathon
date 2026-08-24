import argparse
from pathlib import Path
from .database import Base, engine, SessionLocal
from .config import settings
from .pipeline import ingest_manifest, process_call
from .models import Call

parser=argparse.ArgumentParser(); parser.add_argument("command", choices=["init-db","ingest","process"]); parser.add_argument("--manifest"); parser.add_argument("--limit",type=int)
args=parser.parse_args(); Base.metadata.create_all(engine); db=SessionLocal()
if args.command=="ingest": ingest_manifest(db,Path(args.manifest))
elif args.command=="process":
    q=db.query(Call).filter(Call.status.in_(["queued","failed"]));
    for call in q.limit(args.limit).all(): process_call(db,call,settings.media_root)
