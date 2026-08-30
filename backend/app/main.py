"""FastAPI read API. All expensive work happens in the offline pipeline, never here."""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock, Thread
from time import monotonic
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from .config import settings
from .database import SessionLocal, db_session, engine
from .models import Agent, AttentionContribution, Call, CallAnalysis, Customer, Evidence, MoodEvent, Topic
from .pipeline import ingest_dataset, process_batch
from .security import require_api_access, require_media_access
from .storage import storage

new_files_lock = Lock()
new_files_job: dict[str, Any] = {"status": "IDLE", "discovered": 0, "processed": 0, "failed": 0, "error": None}
read_cache_lock = Lock()
read_cache: dict[tuple[Any, ...], tuple[float, Any]] = {}


def cached_read(key: tuple[Any, ...]) -> Any | None:
    with read_cache_lock:
        cached = read_cache.get(key)
        if cached and cached[0] > monotonic():
            return cached[1]
        read_cache.pop(key, None)
    return None


def cache_read(key: tuple[Any, ...], value: Any, seconds: float = 30.0) -> Any:
    with read_cache_lock:
        read_cache[key] = (monotonic() + seconds, value)
    return value


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Pay the remote connection cost before the first interactive request."""
    with read_cache_lock:
        read_cache.clear()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # The health endpoint remains the authoritative readiness signal.
        pass
    def prewarm(task: str) -> None:
        db = SessionLocal()
        try:
            if task.startswith("calls-"):
                calls(
                    customer_id=None, agent_id=None, intent=None, resolution=None, minimum_attention_score=None,
                    mood=None, started_after=None, started_before=None, minimum_duration_seconds=None,
                    maximum_duration_seconds=None, status=None, search=None, limit=500,
                    offset=int(task.removeprefix("calls-")), db=db,
                )
            elif task == "attention": attention(limit=100, db=db)
            elif task == "customers": customers(search=None, db=db)
            elif task == "trends": trends(days=7, db=db)
            elif task == "agents": agents(db=db)
        finally:
            db.close()
    try:
        with ThreadPoolExecutor(max_workers=7) as pool:
            list(pool.map(prewarm, ("calls-0", "calls-500", "calls-1000", "attention", "customers", "trends", "agents")))
    except SQLAlchemyError:
        pass
    yield


app = FastAPI(title="Call-Centre Radar API", version="1.0.0", description="Persistent, evidence-first call-centre intelligence.", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[value.strip() for value in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
settings.media_root.mkdir(parents=True, exist_ok=True)
router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_access)])


def process_new_call_ids(call_ids: list[str]) -> None:
    db = SessionLocal()
    try:
        calls = db.query(Call).filter(Call.id.in_(call_ids)).all()
        for call in calls:
            storage.upload(call.audio_path, settings.media_root / call.audio_path)
        result = process_batch(db, settings.media_root, call_ids=call_ids)
        with new_files_lock:
            new_files_job.update(status="COMPLETE", **result)
    except Exception as exc:
        with new_files_lock:
            new_files_job.update(status="FAILED", error=str(exc)[:1000])
    finally:
        db.close()


def iso(value: datetime | None) -> str | None:
    # Database timestamps are stored as UTC-naive for cross-database
    # compatibility. Mark API output explicitly as UTC so browser date parsing
    # and offset-aware filtering do not depend on the viewer's local timezone.
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z") if value else None


def evidence_payload(evidence: Evidence | None) -> dict[str, Any] | None:
    if evidence is None:
        return None
    return {
        "id": evidence.id,
        "analysis_type": evidence.analysis_type,
        "claim": evidence.claim,
        "start_ms": evidence.start_ms,
        "end_ms": evidence.end_ms,
        "speaker": evidence.speaker,
        "quote": evidence.quote,
        "transcript_segment_id": evidence.transcript_segment_id,
        "validated": evidence.validated,
    }


def call_summary(call: Call) -> dict[str, Any]:
    analysis = call.analysis
    return {
        "id": call.id,
        "processing_status": call.processing_status,
        "started_at": iso(call.started_at),
        "duration_seconds": call.duration_seconds,
        "customer": {"id": call.customer.id, "name": call.customer.name} if call.customer else None,
        "agent": {"id": call.agent.id, "name": call.agent.name} if call.agent else None,
        "intent_category": analysis.intent_category if analysis else None,
        "resolution_status": analysis.resolution_status if analysis else None,
        "mood_label": dominant_mood([call]),
        "attention_score": analysis.attention_score if analysis else None,
        "attention_band": analysis.attention_band if analysis else None,
    }


def dominant_mood(call_rows: list[Call]) -> str | None:
    """Return the most frequently evidenced customer mood without inventing a sentiment score."""
    counts = Counter(event.mood for call in call_rows for event in call.mood_events)
    return counts.most_common(1)[0][0] if counts else None


def trend_items(current: Counter[str], previous: Counter[str]) -> list[dict[str, Any]]:
    """Build comparison-safe controlled-category trend rows."""
    return [
        {
            "category": category,
            "count": count,
            "previous_count": previous[category],
            "change_percent": round(((count - previous[category]) / previous[category]) * 100, 1)
            if previous[category]
            else None,
        }
        for category, count in current.most_common()
    ]


@app.get("/media/{audio_path:path}", include_in_schema=False)
def local_audio(audio_path: str, _: None = Depends(require_media_access)) -> FileResponse:
    """Serve only local MP3 objects; never expose the archive, database, or scratch files."""
    if settings.storage_provider.lower() != "local":
        raise HTTPException(status_code=404, detail="Local media serving is disabled")
    root = settings.media_root.resolve()
    source = (root / Path(audio_path)).resolve()
    if root not in source.parents or source.suffix.lower() != ".mp3" or not source.is_file():
        raise HTTPException(status_code=404, detail="Recording not found")
    return FileResponse(source, media_type="audio/mpeg", filename=source.name)


def detail_payload(call: Call) -> dict[str, Any]:
    analysis = call.analysis
    evidences = {item.id: item for item in call.evidence_items}
    evidence_by_type: dict[str, list[Evidence]] = defaultdict(list)
    for item in call.evidence_items:
        evidence_by_type[item.analysis_type].append(item)
    mood_events = sorted(call.mood_events, key=lambda item: item.timestamp_ms)
    shift_event = next((item for item in mood_events if analysis and item.id == analysis.mood_shift_event_id), None)
    latest_mood = mood_events[-1] if mood_events else None
    return {
        **call_summary(call),
        "ended_at": iso(call.ended_at),
        "audio": {"url": storage.url_for(call.audio_path), "path": call.audio_path, "duration_seconds": call.duration_seconds},
        "transcript": [
            {"id": item.id, "speaker": item.speaker, "start_ms": item.start_ms, "end_ms": item.end_ms, "text": item.text,
             "confidence": item.confidence}
            for item in call.transcript_segments
        ],
        "analysis": {
            "intent": {
                "category": analysis.intent_category,
                "description": analysis.intent_description,
                "confidence": analysis.intent_confidence,
                "evidence": evidence_payload(evidence_by_type.get("intent", [None])[0]),
            } if analysis and analysis.intent_category else None,
            "resolution": {
                "status": analysis.resolution_status,
                "evidence": evidence_payload(evidence_by_type.get("resolution", [None])[0]),
            } if analysis else None,
            "summary": {
                "value": analysis.summary,
                "word_count": len(analysis.summary.split()) if analysis and analysis.summary else 0,
                "evidence": evidence_payload(evidence_by_type.get("summary", [None])[0]),
            } if analysis and analysis.summary else None,
            "mood": {
                "label": latest_mood.mood,
                "score": latest_mood.score,
                "evidence": evidence_payload(next((value for value in evidence_by_type.get("mood", []) if value.transcript_segment_id == latest_mood.evidence_segment_id), None)),
            } if latest_mood else None,
            "attention": {
                "score": analysis.attention_score,
                "band": analysis.attention_band,
                "contributions": [
                    {"signal": item.signal, "points": item.points, "explanation": item.explanation,
                     "evidence": evidence_payload(evidences.get(item.evidence_id))}
                    for item in sorted(call.attention_contributions, key=lambda value: value.points, reverse=True)
                ],
            } if analysis else None,
            "mood_shift": {
                "from": analysis.mood_shift_from,
                "to": analysis.mood_shift_to,
                "timestamp_ms": shift_event.timestamp_ms if shift_event else None,
                "evidence": evidence_payload(next((item for item in evidence_by_type.get("mood", []) if shift_event and item.transcript_segment_id == shift_event.evidence_segment_id), None)),
            } if analysis and shift_event else None,
            "model_name": analysis.model_name if analysis else None,
        },
        "mood_timeline": [
            {"id": item.id, "timestamp_ms": item.timestamp_ms, "mood": item.mood, "score": item.score,
             "evidence": evidence_payload(next((value for value in evidence_by_type.get("mood", []) if value.transcript_segment_id == item.evidence_segment_id), None))}
            for item in mood_events
        ],
        "evidence": [evidence_payload(item) for item in sorted(call.evidence_items, key=lambda value: value.start_ms)],
        "topics": [{"topic": item.topic, "confidence": item.confidence} for item in call.topics],
        "processing_error": call.processing_error,
    }


def call_query(db: Session):
    return db.query(Call).options(
        joinedload(Call.customer), joinedload(Call.agent), joinedload(Call.analysis), selectinload(Call.transcript_segments),
        selectinload(Call.evidence_items), selectinload(Call.mood_events), selectinload(Call.topics),
        selectinload(Call.attention_contributions).joinedload(AttentionContribution.evidence),
    )


def call_list_query(db: Session):
    """The archive/aggregate views do not need full transcripts or evidence objects."""
    return db.query(Call).options(
        joinedload(Call.customer),
        joinedload(Call.agent),
        joinedload(Call.analysis),
        selectinload(Call.mood_events),
    ).order_by(Call.started_at.desc())


def call_summary_query(db: Session):
    """Project archive fields directly; never hydrate transcripts or relationship collections."""
    dominant_mood = (
        select(MoodEvent.mood)
        .where(MoodEvent.call_id == Call.id)
        .group_by(MoodEvent.mood)
        .order_by(func.count(MoodEvent.id).desc(), MoodEvent.mood)
        .limit(1)
        .correlate(Call)
        .scalar_subquery()
    )
    return db.query(
        Call.id.label("id"),
        Call.processing_status.label("processing_status"),
        Call.started_at.label("started_at"),
        Call.duration_seconds.label("duration_seconds"),
        Customer.id.label("customer_id"),
        Customer.name.label("customer_name"),
        Agent.id.label("agent_id"),
        Agent.name.label("agent_name"),
        CallAnalysis.intent_category.label("intent_category"),
        CallAnalysis.resolution_status.label("resolution_status"),
        CallAnalysis.attention_score.label("attention_score"),
        CallAnalysis.attention_band.label("attention_band"),
        dominant_mood.label("mood_label"),
    ).outerjoin(Call.customer).outerjoin(Call.agent).outerjoin(Call.analysis)


def projected_call_summary(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "processing_status": row.processing_status,
        "started_at": iso(row.started_at),
        "duration_seconds": row.duration_seconds,
        "customer": {"id": row.customer_id, "name": row.customer_name} if row.customer_id else None,
        "agent": {"id": row.agent_id, "name": row.agent_name} if row.agent_id else None,
        "intent_category": row.intent_category,
        "resolution_status": row.resolution_status,
        "mood_label": row.mood_label,
        "attention_score": row.attention_score,
        "attention_band": row.attention_band,
    }


@app.get("/health")
def health() -> dict[str, bool]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"ok": True}


@router.get("/calls")
def calls(
    customer_id: str | None = None, agent_id: str | None = None, intent: str | None = None,
    resolution: str | None = None, minimum_attention_score: int | None = Query(default=None, ge=0, le=100),
    mood: str | None = None, started_after: datetime | None = None, started_before: datetime | None = None,
    minimum_duration_seconds: float | None = Query(default=None, ge=0), maximum_duration_seconds: float | None = Query(default=None, ge=0),
    status: str | None = None, search: str | None = None, limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    # Stored source timestamps are UTC-naive. Convert incoming offset-aware
    # query values to that same timeline instead of merely dropping their UTC
    # offset (which would shift date-filter results by hours).
    if started_after and started_after.tzinfo:
        started_after = started_after.astimezone(UTC).replace(tzinfo=None)
    if started_before and started_before.tzinfo:
        started_before = started_before.astimezone(UTC).replace(tzinfo=None)
    cache_key = ("calls", customer_id, agent_id, intent, resolution, minimum_attention_score, mood, started_after, started_before, minimum_duration_seconds, maximum_duration_seconds, status, search, limit, offset)
    cached = cached_read(cache_key)
    if cached is not None:
        return cached
    query = call_summary_query(db).order_by(Call.started_at.desc())
    if customer_id: query = query.filter(Call.customer_id == customer_id)
    if agent_id: query = query.filter(Call.agent_id == agent_id)
    if status: query = query.filter(Call.processing_status == status)
    if intent: query = query.filter(CallAnalysis.intent_category == intent)
    if resolution: query = query.filter(CallAnalysis.resolution_status == resolution)
    if minimum_attention_score is not None: query = query.filter(CallAnalysis.attention_score >= minimum_attention_score)
    if mood: query = query.filter(Call.mood_events.any(MoodEvent.mood == mood))
    if started_after: query = query.filter(Call.started_at >= started_after)
    if started_before: query = query.filter(Call.started_at <= started_before)
    if minimum_duration_seconds is not None: query = query.filter(Call.duration_seconds >= minimum_duration_seconds)
    if maximum_duration_seconds is not None: query = query.filter(Call.duration_seconds <= maximum_duration_seconds)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(or_(Call.id.ilike(pattern), Customer.name.ilike(pattern), Agent.name.ilike(pattern)))
    return cache_read(cache_key, [projected_call_summary(row) for row in query.offset(offset).limit(limit).all()])


@router.get("/calls/{call_id}")
def call_detail(call_id: str, db: Session = Depends(db_session)) -> dict[str, Any]:
    cache_key = ("call-detail", call_id)
    cached = cached_read(cache_key)
    if cached is not None:
        return cached
    call = call_query(db).filter(Call.id == call_id).first()
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return cache_read(cache_key, detail_payload(call))


@router.get("/calls/{call_id}/audio")
def call_audio(call_id: str, db: Session = Depends(db_session)) -> RedirectResponse:
    call = db.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return RedirectResponse(storage.url_for(call.audio_path), status_code=307)


@router.get("/attention")
def attention(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(db_session)) -> list[dict[str, Any]]:
    cache_key = ("attention", limit)
    cached = cached_read(cache_key)
    if cached is not None:
        return cached
    rows = call_summary_query(db).filter(CallAnalysis.attention_score > 0).order_by(CallAnalysis.attention_score.desc()).limit(limit).all()
    return cache_read(cache_key, [projected_call_summary(row) for row in rows])


@router.get("/customers")
def customers(search: str | None = None, db: Session = Depends(db_session)) -> list[dict[str, Any]]:
    cache_key = ("customers", search)
    cached = cached_read(cache_key)
    if cached is not None:
        return cached
    rows = db.query(Customer).options(
        selectinload(Customer.calls).joinedload(Call.analysis),
        selectinload(Customer.calls).selectinload(Call.mood_events),
    ).all()
    needle = search.lower() if search else None
    result = []
    for customer in rows:
        if needle and needle not in f"{customer.id} {customer.name or ''}".lower(): continue
        calls = customer.calls
        result.append({
            "id": customer.id,
            "name": customer.name,
            "call_count": len(calls),
            "unresolved_count": sum(1 for call in calls if call.analysis and call.analysis.resolution_status == "UNRESOLVED"),
            "average_mood": dominant_mood(calls),
            "last_contact": iso(max((call.started_at for call in calls if call.started_at), default=None)),
        })
    return cache_read(cache_key, sorted(result, key=lambda item: item["name"] or item["id"]))


@router.get("/customers/{customer_id}")
def customer_detail(customer_id: str, db: Session = Depends(db_session)) -> dict[str, Any]:
    customer = db.query(Customer).options(
        joinedload(Customer.calls).joinedload(Call.analysis),
        joinedload(Customer.calls).joinedload(Call.agent),
        joinedload(Customer.calls).joinedload(Call.mood_events),
    ).filter(Customer.id == customer_id).first()
    if customer is None: raise HTTPException(status_code=404, detail="Customer not found")
    calls = sorted(customer.calls, key=lambda value: value.started_at or datetime.min, reverse=True)
    return {
        "id": customer.id,
        "name": customer.name,
        "call_count": len(calls),
        "unresolved_count": sum(1 for call in calls if call.analysis and call.analysis.resolution_status == "UNRESOLVED"),
        "average_mood": dominant_mood(calls),
        "last_contact": iso(calls[0].started_at) if calls else None,
        "calls": [call_summary(call) for call in calls],
    }


@router.get("/customers/{customer_id}/calls")
def customer_calls(customer_id: str, db: Session = Depends(db_session)) -> list[dict[str, Any]]:
    return customer_detail(customer_id, db)["calls"]


@router.get("/trends")
def trends(days: int = Query(default=7, ge=1, le=365), db: Session = Depends(db_session)) -> dict[str, Any]:
    cache_key = ("trends", days)
    cached = cached_read(cache_key)
    if cached is not None:
        return cached
    ready = [call for call in call_list_query(db).all() if call.analysis and call.analysis.intent_category]
    latest = max((call.started_at for call in ready if call.started_at), default=None)
    if latest:
        start, previous_start = latest - timedelta(days=days), latest - timedelta(days=days * 2)
        current = [call for call in ready if call.started_at and call.started_at >= start]
        previous = [call for call in ready if call.started_at and previous_start <= call.started_at < start]
    else:
        current, previous = ready, []
    current_intents = Counter(call.analysis.intent_category for call in current)
    previous_intents = Counter(call.analysis.intent_category for call in previous)
    current_resolutions = Counter(call.analysis.resolution_status for call in current if call.analysis.resolution_status != "UNKNOWN")
    previous_resolutions = Counter(call.analysis.resolution_status for call in previous if call.analysis.resolution_status != "UNKNOWN")
    current_moods = Counter(event.mood for call in current for event in call.mood_events)
    previous_moods = Counter(event.mood for call in previous for event in call.mood_events)
    return cache_read(cache_key, {
        "period_days": days,
        "reference_end": iso(latest),
        "issues": trend_items(current_intents, previous_intents),
        "resolutions": trend_items(current_resolutions, previous_resolutions),
        "moods": trend_items(current_moods, previous_moods),
        "processed_calls": len(ready),
    })


@router.get("/agents")
def agents(db: Session = Depends(db_session)) -> list[dict[str, Any]]:
    cache_key = ("agents",)
    cached = cached_read(cache_key)
    if cached is not None:
        return cached
    rows = db.query(Agent).options(
        selectinload(Agent.calls).joinedload(Call.analysis),
        selectinload(Agent.calls).selectinload(Call.topics),
        selectinload(Agent.calls).selectinload(Call.mood_events),
        selectinload(Agent.calls).selectinload(Call.attention_contributions),
    ).all()
    result = []
    for agent in rows:
        calls = agent.calls
        analyzed = [call for call in calls if call.analysis]
        resolutions = [call for call in analyzed if call.analysis.resolution_status != "UNKNOWN"]
        escalated = [call for call in analyzed if any(item.signal == "escalation_requested" for item in call.attention_contributions)]
        durations = [call.duration_seconds for call in calls if call.duration_seconds is not None]
        result.append({
            "id": agent.id,
            "name": agent.name,
            "call_count": len(calls),
            "average_handle_seconds": round(sum(durations) / len(durations), 1) if durations else None,
            "resolution_rate": round(sum(1 for call in resolutions if call.analysis.resolution_status == "RESOLVED") / len(resolutions) * 100, 1) if resolutions else None,
            "escalation_rate": round(len(escalated) / len(analyzed) * 100, 1) if analyzed else None,
            "average_attention_score": round(sum(call.analysis.attention_score for call in analyzed) / len(analyzed), 1) if analyzed else None,
            "review_call_count": sum(1 for call in analyzed if call.analysis.attention_score >= 50),
        })
    return cache_read(cache_key, sorted(result, key=lambda item: item["name"] or item["id"]))


@router.get("/agents/{agent_id}")
def agent_detail(agent_id: str, db: Session = Depends(db_session)) -> dict[str, Any]:
    agent = db.query(Agent).options(
        joinedload(Agent.calls).joinedload(Call.analysis),
        joinedload(Agent.calls).joinedload(Call.customer),
        joinedload(Agent.calls).joinedload(Call.topics),
        joinedload(Agent.calls).joinedload(Call.mood_events),
    ).filter(Agent.id == agent_id).first()
    if agent is None: raise HTTPException(status_code=404, detail="Agent not found")
    base = next((item for item in agents(db) if item["id"] == agent_id), None)
    topics = Counter(topic.topic for call in agent.calls for topic in call.topics)
    return {**(base or {"id": agent.id, "name": agent.name}), "common_issue_types": [{"topic": topic, "count": count} for topic, count in topics.most_common()], "calls_needing_review": [call_summary(call) for call in agent.calls if call.analysis and call.analysis.attention_score >= 50], "calls": [call_summary(call) for call in agent.calls]}


@router.get("/processing/progress")
def processing_progress(db: Session = Depends(db_session)) -> dict[str, Any]:
    counts = Counter(status for (status,) in db.query(Call.processing_status).all())
    total, ready = sum(counts.values()), counts.get("READY", 0)
    return {"total": total, "ready": ready, "percent_ready": round((ready / total) * 100, 1) if total else 0, "by_status": dict(sorted(counts.items()))}


@router.get("/processing/new-files")
def new_files_status() -> dict[str, Any]:
    with new_files_lock:
        return dict(new_files_job)


@router.post("/processing/new-files", status_code=202)
def process_new_files(db: Session = Depends(db_session)) -> dict[str, Any]:
    """Ingest matched files not already persisted and process only those calls."""
    with new_files_lock:
        if new_files_job["status"] == "RUNNING":
            raise HTTPException(status_code=409, detail="A new-files processing job is already running")

    existing_ids = {call_id for (call_id,) in db.query(Call.id).all()}
    ingestion = ingest_dataset(db, settings.dataset_root, settings.media_root)
    new_ids = [call_id for (call_id,) in db.query(Call.id).filter(~Call.id.in_(existing_ids)).all()]

    with new_files_lock:
        new_files_job.update(
            status="RUNNING" if new_ids else "COMPLETE",
            discovered=len(new_ids),
            processed=0,
            failed=0,
            error=None,
            ingestion=ingestion,
        )
        response = dict(new_files_job)
    if new_ids:
        Thread(target=process_new_call_ids, args=(new_ids,), daemon=True, name="callradar-new-files").start()
    return response


app.include_router(router)

# Legacy aliases keep the first scaffold usable while clients migrate to /api/v1.
app.add_api_route("/calls", calls, methods=["GET"], dependencies=[Depends(require_api_access)])
app.add_api_route("/calls/{call_id}", call_detail, methods=["GET"], dependencies=[Depends(require_api_access)])
app.add_api_route("/attention", attention, methods=["GET"], dependencies=[Depends(require_api_access)])
app.add_api_route("/customers", customers, methods=["GET"], dependencies=[Depends(require_api_access)])
app.add_api_route("/trends", trends, methods=["GET"], dependencies=[Depends(require_api_access)])
app.add_api_route("/agents", agents, methods=["GET"], dependencies=[Depends(require_api_access)])
