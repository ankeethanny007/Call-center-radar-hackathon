from datetime import UTC, datetime
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import app.pipeline as pipeline
import app.cli as cli
from app.analysis import RuleAnalysisEngine, validate_candidate_evidence
from app.database import Base
from app.models import Call, CallAnalysis, TranscriptSegment
from app.storage import storage


def make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'pipeline.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def test_epoch_timestamps_are_normalized_to_naive_utc() -> None:
    milliseconds = 1_700_000_000_000
    expected = datetime.fromtimestamp(milliseconds / 1000, tz=UTC).replace(tzinfo=None)

    assert pipeline.parse_datetime(milliseconds) == expected
    assert pipeline.parse_datetime(0) == datetime(1970, 1, 1)
    assert pipeline.parse_datetime("2023-11-14T17:13:20-05:00") == expected


def test_word_timestamps_split_phrases_separated_by_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline.settings, "whisper_utterance_gap_seconds", 1.0)
    monkeypatch.setattr(pipeline.settings, "whisper_max_utterance_seconds", 12.0)
    words = [
        SimpleNamespace(start=10.0, end=10.4, word=" Wednesday"),
        SimpleNamespace(start=10.4, end=10.8, word="."),
        SimpleNamespace(start=57.0, end=57.3, word=" Four"),
        SimpleNamespace(start=57.3, end=58.0, word=" thirty p.m."),
    ]

    assert pipeline.split_word_timestamps(words, -0.2) == [
        (10_000, 10_800, "Wednesday.", -0.2),
        (57_000, 58_000, "Four thirty p.m.", -0.2),
    ]


def test_analyzed_call_finalizes_without_reinvoking_analysis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = make_session(tmp_path)
    call = Call(id="already-analysed", audio_path="audio/already-analysed.mp3", processing_status="ANALYZED")
    db.add_all([call, CallAnalysis(call=call)])
    db.commit()

    def model_must_not_run():
        raise AssertionError("an ANALYZED call must not invoke the analysis engine")

    monkeypatch.setattr(pipeline, "get_analysis_engine", model_must_not_run)
    pipeline.process_call(db, call, tmp_path / "media")

    db.refresh(call)
    assert call.processing_status == "READY"
    assert call.processed_at is not None
    db.close()


def test_reanalysis_replaces_mood_shift_with_foreign_keys_enforced(tmp_path: Path) -> None:
    """PostgreSQL enforces this relationship; make the SQLite test do the same."""
    engine = create_engine(f"sqlite:///{tmp_path / 'foreign-keys.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    call = Call(id="reanalysis", audio_path="audio/reanalysis.mp3")
    db.add_all(
        [
            call,
            TranscriptSegment(call=call, speaker="customer", start_ms=0, end_ms=800, text="I am concerned about my card."),
            TranscriptSegment(call=call, speaker="customer", start_ms=900, end_ms=1800, text="I am frustrated and this is still not resolved."),
        ]
    )
    db.commit()

    for _ in range(2):
        turns = list(call.transcript_segments)
        candidate = RuleAnalysisEngine().analyse(turns)
        candidate = validate_candidate_evidence(candidate, {turn.id: turn for turn in turns}, RuleAnalysisEngine())
        pipeline.persist_analysis(db, call, candidate, "rules")
        db.commit()
        db.refresh(call)

    assert call.analysis is not None
    assert call.analysis.mood_shift_event_id is not None
    assert len(call.mood_events) == 2
    db.close()


def test_processing_cleans_channel_scratch_after_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = make_session(tmp_path)
    media_root = tmp_path / "media"
    source = media_root / "audio" / "success.mp3"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"placeholder audio")
    call = Call(id="success", audio_path="audio/success.mp3", processing_status="DISCOVERED")
    db.add(call)
    db.commit()

    monkeypatch.setattr(pipeline, "ffprobe_duration", lambda _source: 12.0)
    monkeypatch.setattr(pipeline, "get_analysis_engine", RuleAnalysisEngine)

    def fake_transcribe(_source: Path, channel: int, output: Path):
        output.write_bytes(b"transient wav")
        if channel == 0:
            return [(0, 900, "Hello, how can I help you?", -0.1)]
        return [(200, 1100, "My card is missing.", -0.2)]

    monkeypatch.setattr(pipeline, "transcribe_channel", fake_transcribe)
    pipeline.process_call(db, call, media_root)

    db.refresh(call)
    assert call.processing_status == "READY"
    assert not (media_root / ".work").exists()
    db.close()


def test_failed_analysis_retry_reuses_persisted_transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = make_session(tmp_path)
    call = Call(id="analysis-retry", audio_path="audio/analysis-retry.mp3", processing_status="FAILED")
    db.add_all([
        call,
        TranscriptSegment(call=call, speaker="customer", start_ms=1_000, end_ms=2_000, text="Thank you. Bye."),
    ])
    db.commit()

    monkeypatch.setattr(pipeline, "get_analysis_engine", RuleAnalysisEngine)

    def transcription_must_not_run(*_args, **_kwargs):
        raise AssertionError("a persisted transcript must be reused for an analysis retry")

    monkeypatch.setattr(pipeline, "transcribe_channel", transcription_must_not_run)
    pipeline.process_call(db, call, tmp_path / "media")

    db.refresh(call)
    assert call.processing_status == "READY"
    assert call.analysis is not None
    assert not call.mood_events
    db.close()


def test_processing_cleans_channel_scratch_after_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = make_session(tmp_path)
    media_root = tmp_path / "media"
    source = media_root / "audio" / "failure.mp3"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"placeholder audio")
    call = Call(id="failure", audio_path="audio/failure.mp3", processing_status="DISCOVERED")
    db.add(call)
    db.commit()

    monkeypatch.setattr(pipeline, "ffprobe_duration", lambda _source: 12.0)

    def fail_after_writing_wav(_source: Path, _channel: int, output: Path):
        output.write_bytes(b"transient wav")
        raise RuntimeError("simulated transcription failure")

    monkeypatch.setattr(pipeline, "transcribe_channel", fail_after_writing_wav)
    with pytest.raises(RuntimeError, match="simulated transcription failure"):
        pipeline.process_call(db, call, media_root)

    db.refresh(call)
    assert call.processing_status == "FAILED"
    assert not (media_root / ".work").exists()
    db.close()


def test_materialize_downloads_only_when_local_audio_is_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    media_root = tmp_path / "media"
    scratch = tmp_path / "scratch"
    requested: list[tuple[str, Path]] = []

    def fake_download(relative_path: str, destination: Path) -> Path:
        requested.append((relative_path, destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"downloaded mp3")
        return destination

    monkeypatch.setattr(storage, "download", fake_download)
    remote_copy = storage.materialize("audio/remote.mp3", media_root, scratch)
    assert remote_copy == scratch / "source.mp3"
    assert requested == [("audio/remote.mp3", scratch / "source.mp3")]

    local = media_root / "audio" / "local.mp3"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"local mp3")
    assert storage.materialize("audio/local.mp3", media_root, scratch) == local
    assert len(requested) == 1


def test_reanalyse_queues_only_ready_calls_with_transcripts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    db = make_session(tmp_path)
    ready = Call(id="ready", audio_path="audio/ready.mp3", processing_status="READY")
    no_transcript = Call(id="empty", audio_path="audio/empty.mp3", processing_status="READY")
    db.add_all(
        [
            ready,
            no_transcript,
            TranscriptSegment(call=ready, speaker="customer", start_ms=0, end_ms=500, text="Please help."),
        ]
    )
    db.commit()
    seen: list[str] = []

    def fake_process_batch(_db: Session, _media_root: Path, **kwargs: object) -> dict[str, int]:
        seen.extend(kwargs["call_ids"])
        return {"processed": 1, "failed": 0}

    monkeypatch.setattr(cli, "upgrade_database", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli, "process_batch", fake_process_batch)
    monkeypatch.setattr(sys, "argv", ["callradar", "reanalyse"])
    cli.main()

    assert seen == ["ready"]
    assert '"queued_for_reanalysis": 1' in capsys.readouterr().out
