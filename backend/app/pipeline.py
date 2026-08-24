import json, subprocess
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from .models import Call, Customer, Turn, Analysis
from .analysis import analyse

def ingest_manifest(db: Session, manifest: Path):
    """Manifest schema is documented in README; no assumptions about source JSON are made."""
    for row in json.loads(manifest.read_text()):
        call_id, audio = row["call_id"], row["audio_path"]
        if db.get(Call, call_id): continue
        customer_id = row.get("customer_id")
        if customer_id and not db.get(Customer, customer_id): db.add(Customer(id=customer_id, display_name=row.get("customer_name")))
        db.add(Call(id=call_id, customer_id=customer_id, audio_path=audio, metadata=row.get("metadata", {})))
    db.commit()

def transcribe_channel(audio: Path, channel: int, output: Path):
    subprocess.run(["ffmpeg", "-y", "-i", str(audio), "-map_channel", f"0.0.{channel}", "-ar", "16000", str(output)], check=True)
    from faster_whisper import WhisperModel
    model = WhisperModel("small", compute_type="int8")
    return [(int(s.start*1000), int(s.end*1000), s.text.strip()) for s in model.transcribe(str(output), vad_filter=True)[0] if s.text.strip()]

def process_call(db: Session, call: Call, media_root: Path):
    call.status, call.error = "processing", None; db.commit()
    try:
        source = media_root / call.audio_path
        scratch = media_root / ".work" / call.id; scratch.mkdir(parents=True, exist_ok=True)
        # Channel attribution is never inferred: 0=agent (left), 1=customer (right).
        records = [("agent", *x) for x in transcribe_channel(source, 0, scratch/"agent.wav")] + [("customer", *x) for x in transcribe_channel(source, 1, scratch/"customer.wav")]
        records.sort(key=lambda r: r[1])
        db.query(Turn).filter_by(call_id=call.id).delete()
        for speaker, start, end, text in records: db.add(Turn(call_id=call.id, speaker=speaker, start_ms=start, end_ms=end, text=text))
        db.flush(); result = analyse(db.query(Turn).filter_by(call_id=call.id).order_by(Turn.start_ms).all())
        db.merge(Analysis(call_id=call.id, **result)); call.status="complete"; call.processed_at=datetime.utcnow(); db.commit()
    except Exception as exc:
        call.status, call.error = "failed", str(exc); db.commit(); raise
