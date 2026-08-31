from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main as main
from app.database import Base, db_session
from app.main import app
from app.models import Agent, AttentionContribution, Call, CallAnalysis, Customer, Evidence, TranscriptSegment


def test_ready_call_detail_contains_seekable_evidence(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    customer = Customer(id="customer-1", name="Sam Smith")
    agent = Agent(id="agent-1", name="Alex")
    call = Call(id="call-1", customer=customer, agent=agent, audio_path="audio/call-1.mp3", processing_status="READY", duration_seconds=30, started_at=datetime(2024, 1, 1, 12))
    segment = TranscriptSegment(call=call, speaker="customer", start_ms=2_000, end_ms=4_000, text="This is still not resolved.")
    session.add_all([customer, agent, call, segment])
    session.flush()
    evidence = Evidence(call=call, analysis_type="resolution", claim="UNRESOLVED", start_ms=2_000, end_ms=4_000, speaker="customer", quote=segment.text, transcript_segment_id=segment.id, validated=True)
    session.add(evidence)
    session.flush()
    analysis = CallAnalysis(call=call, resolution_status="UNRESOLVED", attention_score=25, attention_band="LOW")
    contribution = AttentionContribution(call=call, signal="issue_unresolved", points=25, explanation="Customer explicitly indicated the issue remained unresolved.", evidence_id=evidence.id)
    session.add_all([analysis, contribution])
    session.commit()
    session.close()

    def override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_session] = override_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/calls/call-1")
            audio = client.get("/api/v1/calls/call-1/audio", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    detail = response.json()
    assert detail["started_at"].endswith("Z")
    assert detail["audio"]["url"].endswith("audio/call-1.mp3")
    assert detail["transcript"][0]["start_ms"] == 2_000
    contribution = detail["analysis"]["attention"]["contributions"][0]
    assert contribution["evidence"]["start_ms"] == 2_000
    assert contribution["evidence"]["quote"] == "This is still not resolved."
    assert audio.status_code == 307
    assert audio.headers["location"].endswith("audio/call-1.mp3")


def test_call_archive_accepts_pagination(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'pagination.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    session.add_all([
        Call(id="call-a", audio_path="audio/call-a.mp3", processing_status="DISCOVERED"),
        Call(id="call-b", audio_path="audio/call-b.mp3", processing_status="DISCOVERED"),
    ])
    session.commit()
    session.close()

    def override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_session] = override_db
    try:
        response = TestClient(app).get("/api/v1/calls?limit=1&offset=1")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_call_date_filter_normalizes_offset_to_utc(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'date-filter.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    # This is 01:00 UTC, which is earlier than midnight in UTC-05 (05:00 UTC).
    session.add(Call(id="before-offset-cutoff", audio_path="audio/call.mp3", started_at=datetime(2024, 1, 1, 1)))
    session.commit()
    session.close()

    def override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_session] = override_db
    try:
        response = TestClient(app).get("/api/v1/calls?started_after=2024-01-01T00:00:00-05:00")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == []


def test_processing_action_resumes_existing_non_terminal_calls(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'resume.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    db.add_all([
        Call(id="ready", audio_path="audio/ready.mp3", processing_status="READY"),
        Call(id="pending-a", audio_path="audio/pending-a.mp3", processing_status="DISCOVERED"),
        Call(id="pending-b", audio_path="audio/pending-b.mp3", processing_status="ANALYZING"),
    ])
    db.commit()

    started: dict[str, object] = {}

    class FakeThread:
        def __init__(self, *, target, args, **_kwargs):
            started.update(target=target, args=args)

        def start(self):
            started["started"] = True

    monkeypatch.setattr(main, "discover_new_file_ids", lambda _existing: [])
    monkeypatch.setattr(main, "Thread", FakeThread)
    with main.new_files_lock:
        main.new_files_job.update(status="IDLE")

    response = main.process_new_files(db)

    assert response["status"] == "RUNNING"
    assert response["action"] == "resumed"
    assert response["discovered"] == 0
    assert response["resumed"] == 2
    assert response["queued"] == 2
    queued_ids, new_ids = started["args"]
    assert set(queued_ids) == {"pending-a", "pending-b"}
    assert new_ids == []
    assert started["started"] is True
    db.close()


def test_processing_action_reports_an_existing_job(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'running.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    db.add(Call(id="pending", audio_path="audio/pending.mp3", processing_status="TRANSCRIBING"))
    db.commit()
    with main.new_files_lock:
        main.new_files_job.update(status="RUNNING", queued=4)

    response = main.process_new_files(db)

    assert response["action"] == "already_running"
    assert response["remaining"] == 1
    with main.new_files_lock:
        main.new_files_job.update(status="IDLE")
    db.close()
