from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from .config import settings
from .database import Base, engine, db_session
from .models import Call, Customer, Turn

Base.metadata.create_all(engine)
app = FastAPI(title="Call-Centre Radar API")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_methods=["*"], allow_headers=["*"])
if settings.media_root.exists(): app.mount("/media", StaticFiles(directory=settings.media_root), name="media")

@app.get("/health")
def health(): return {"ok": True}
@app.get("/calls")
def calls(db: Session = Depends(db_session)):
    return [{"id": c.id, "customer_id": c.customer_id, "status": c.status, "attention_score": c.analysis.attention_score if c.analysis else None} for c in db.query(Call).all()]
@app.get("/calls/{call_id}")
def call_detail(call_id: str, db: Session = Depends(db_session)):
    call = db.get(Call, call_id)
    if not call: raise HTTPException(404, "Call not found")
    return {"id": call.id, "customer_id": call.customer_id, "status": call.status, "audio_url": f"/media/{call.audio_path}", "metadata": call.metadata, "analysis": {"intent":call.analysis.intent,"mood":call.analysis.mood,"resolution":call.analysis.resolution,"summary":call.analysis.summary,"attention_score":call.analysis.attention_score,"attention_evidence":call.analysis.attention_evidence} if call.analysis else None, "turns":[{"id":t.id,"speaker":t.speaker,"start_ms":t.start_ms,"end_ms":t.end_ms,"text":t.text} for t in sorted(call.turns,key=lambda x:x.start_ms)]}
@app.get("/attention")
def attention(db: Session = Depends(db_session)):
    return sorted([x for x in calls(db) if x["attention_score"] is not None], key=lambda x:x["attention_score"], reverse=True)
@app.get("/customers")
def customers(db: Session = Depends(db_session)):
    return [{"id":c.id,"display_name":c.display_name,"call_count":len(c.calls)} for c in db.query(Customer).all()]

@app.get("/trends")
def trends(db: Session = Depends(db_session)):
    """Only labels actually persisted by the evidence-first analyzer are aggregated."""
    buckets: dict[str, int] = {}
    for call in db.query(Call).all():
        if call.analysis and call.analysis.intent:
            label = call.analysis.intent["label"]
            buckets[label] = buckets.get(label, 0) + 1
    return {"intent_counts": buckets, "processed_calls": db.query(Call).filter_by(status="complete").count()}

@app.get("/agents")
def agents(db: Session = Depends(db_session)):
    """Agent identifiers are optional source metadata, never guessed from speech."""
    stats: dict[str, dict] = {}
    for call in db.query(Call).all():
        agent_id = call.metadata.get("agent_id")
        if not agent_id: continue
        row = stats.setdefault(agent_id, {"agent_id": agent_id, "call_count": 0, "attention_total": 0, "scored_calls": 0})
        row["call_count"] += 1
        if call.analysis and call.analysis.attention_score is not None:
            row["attention_total"] += call.analysis.attention_score; row["scored_calls"] += 1
    return [{**v, "average_attention_score": round(v["attention_total"] / v["scored_calls"], 1) if v["scored_calls"] else None} for v in stats.values()]
