"""Offline, resumable dataset processing for Call-Centre Radar."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy.orm import Session

from .analysis import ATTENTION_WEIGHTS, AnalysisCandidate, EvidencePointer, attention_band, get_analysis_engine, pointer_is_valid, validate_candidate_evidence
from .config import settings
from .models import (
    Agent,
    AttentionContribution,
    Call,
    CallAnalysis,
    Customer,
    Evidence,
    MoodEvent,
    Topic,
    TranscriptSegment,
)
from .storage import storage

ACTIVE_STATUSES = ("DISCOVERED", "VALIDATED", "TRANSCRIBING", "TRANSCRIBED", "ANALYZING", "ANALYZED")


def ffmpeg_binary() -> str:
    """Prefer system FFmpeg; use the packaged FFmpeg binary for local development."""
    binary = shutil.which("ffmpeg")
    if binary:
        return binary
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (int, float)):
        # Metadata epoch values might be seconds or milliseconds.
        epoch = value / 1000 if abs(value) > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(epoch, tz=UTC).replace(tzinfo=None)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            return None
    return None


def first_present(source: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return value
    return None


def identity_key(kind: str, name: str | None) -> str | None:
    """The source has names but no stable participant IDs across calls."""
    if not name:
        return None
    normalized = " ".join(name.lower().split())
    return f"{kind}-{hashlib.sha256(normalized.encode()).hexdigest()[:20]}"


def metadata_record(call_id: str, audio_path: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Small compatibility adapter for common source field names.

    The exact mapping is adjusted after inspecting the supplied metadata. Original JSON is
    always retained intact in source_metadata, so no source information is destroyed.
    """
    # Verified CallRadar source schema uses caller/agent objects rather than IDs.
    caller = metadata.get("caller") if isinstance(metadata.get("caller"), dict) else {}
    source_agent = metadata.get("agent") if isinstance(metadata.get("agent"), dict) else {}
    customer = metadata.get("customer") if isinstance(metadata.get("customer"), dict) else caller
    agent = source_agent
    customer_name = first_present(metadata, ("customer_name", "customerName")) or first_present(customer, ("name", "full_name"))
    if not customer_name and isinstance(caller.get("metadata"), dict):
        customer_name = caller["metadata"].get("first and last name")
    agent_name = first_present(metadata, ("agent_name", "agentName")) or first_present(agent, ("name", "full_name"))
    if not agent_name and isinstance(agent.get("metadata"), dict):
        agent_name = agent["metadata"].get("agent_name")
    customer_id = first_present(metadata, ("customer_id", "customerId", "customerID")) or identity_key("customer", customer_name)
    agent_id = first_present(metadata, ("agent_id", "agentId", "agentID")) or identity_key("agent", agent_name)
    started_at = first_present(metadata, ("start_time_ms", "started_at", "startedAt", "start_time", "startTime", "timestamp", "call_start"))
    ended_at = first_present(metadata, ("end_time_ms", "ended_at", "endedAt", "end_time", "endTime", "call_end"))
    duration = first_present(metadata, ("duration_seconds", "durationSeconds", "duration", "call_duration"))
    try:
        duration = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration = None
    return {
        "call_id": call_id,
        "audio_path": audio_path,
        "customer_id": str(customer_id) if customer_id is not None else None,
        "customer_name": str(customer_name) if customer_name is not None else None,
        "agent_id": str(agent_id) if agent_id is not None else None,
        "agent_name": str(agent_name) if agent_name is not None else None,
        "started_at": parse_datetime(started_at),
        "ended_at": parse_datetime(ended_at),
        "duration_seconds": duration,
        "metadata": metadata,
    }


def validate_metadata_shape(call_id: str, metadata: dict[str, Any]) -> str | None:
    """Validate the verified CallRadar source contract without deriving new semantics."""
    required = ("sid", "session", "start_time_ms", "end_time_ms", "agent", "caller", "labels")
    missing = [key for key in required if key not in metadata]
    if missing:
        return f"Metadata is missing required fields: {', '.join(missing)}"
    if metadata.get("sid") != call_id:
        return "Metadata sid does not match filename/call ID"
    if not isinstance(metadata["agent"], dict) or not isinstance(metadata["caller"], dict):
        return "Agent/caller metadata must be objects"
    if not isinstance(metadata["agent"].get("metadata"), dict) or not isinstance(metadata["caller"].get("metadata"), dict):
        return "Agent/caller metadata subobjects are required"
    if not metadata["agent"]["metadata"].get("agent_name") or not metadata["caller"]["metadata"].get("first and last name"):
        return "Agent and caller display names are required"
    return None


def upsert_call(db: Session, row: dict[str, Any]) -> Call:
    customer_id, agent_id = row.get("customer_id"), row.get("agent_id")
    if customer_id:
        customer = db.get(Customer, customer_id)
        if customer is None:
            db.add(Customer(id=customer_id, name=row.get("customer_name")))
            # Session autoflush is deliberately disabled; make the unique identity visible
            # before the next matched call with the same source name is ingested.
            db.flush()
        elif row.get("customer_name"):
            customer.name = row["customer_name"]
    if agent_id:
        agent = db.get(Agent, agent_id)
        if agent is None:
            db.add(Agent(id=agent_id, name=row.get("agent_name")))
            db.flush()
        elif row.get("agent_name"):
            agent.name = row["agent_name"]

    call = db.get(Call, row["call_id"])
    if call is None:
        call = Call(id=row["call_id"], audio_path=row["audio_path"], processing_status="DISCOVERED")
        db.add(call)
    call.customer_id = customer_id
    call.agent_id = agent_id
    call.started_at = row.get("started_at")
    call.ended_at = row.get("ended_at")
    call.duration_seconds = row.get("duration_seconds")
    call.audio_path = row["audio_path"]
    call.source_metadata = row.get("metadata", {})
    return call


def ingest_manifest(db: Session, manifest: Path) -> int:
    """Import the documented neutral manifest format for custom data sources."""
    records = json.loads(manifest.read_text())
    if not isinstance(records, list):
        raise ValueError("Manifest must contain a JSON array")
    for record in records:
        if "call_id" not in record or "audio_path" not in record:
            raise ValueError("Every manifest record needs call_id and audio_path")
        row = metadata_record(record["call_id"], record["audio_path"], record.get("metadata", {}))
        for key in ("customer_id", "customer_name", "agent_id", "agent_name", "duration_seconds"):
            if key in record:
                row[key] = record[key]
        for key in ("started_at", "ended_at"):
            if key in record:
                row[key] = parse_datetime(record[key])
        upsert_call(db, row)
    db.commit()
    return len(records)


def ingest_dataset(db: Session, dataset_root: Path, media_root: Path) -> dict[str, int]:
    """Discover matched audio/metadata pairs from the supplied archive after extraction."""
    audio_dir, metadata_dir = dataset_root / "audio", dataset_root / "metadata"
    if not audio_dir.is_dir() or not metadata_dir.is_dir():
        raise ValueError(f"Expected audio/ and metadata/ under {dataset_root}")
    audio_by_id = {item.stem: item for item in audio_dir.glob("*.mp3")}
    metadata_by_id = {item.stem: item for item in metadata_dir.glob("*.json")}
    matched = sorted(audio_by_id.keys() & metadata_by_id.keys())
    invalid_metadata = 0
    for call_id in matched:
        metadata = json.loads(metadata_by_id[call_id].read_text())
        metadata_error = validate_metadata_shape(call_id, metadata)
        if metadata_error:
            invalid_metadata += 1
            continue
        relative_audio = str(audio_by_id[call_id].relative_to(media_root))
        upsert_call(db, metadata_record(call_id, relative_audio, metadata))
    db.commit()
    return {"audio": len(audio_by_id), "metadata": len(metadata_by_id), "matched": len(matched) - invalid_metadata, "invalid_metadata": invalid_metadata, "audio_only": len(audio_by_id.keys() - metadata_by_id.keys()), "metadata_only": len(metadata_by_id.keys() - audio_by_id.keys())}


def ffprobe_duration(path: Path) -> float | None:
    probe = shutil.which("ffprobe")
    if not probe:
        try:
            import av
            with av.open(str(path)) as container:
                return float(container.duration / av.time_base) if container.duration is not None else None
        except Exception:
            return None
    result = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=False,
    )
    try:
        return float(result.stdout.strip()) if result.returncode == 0 else None
    except ValueError:
        return None


def create_scratch_dir(media_root: Path, call_id: str) -> Path:
    """Create a unique per-call work area that is always safe to remove."""
    work_root = media_root / ".work"
    work_root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(call_id.encode()).hexdigest()[:16]
    return Path(tempfile.mkdtemp(prefix=f"{digest}-", dir=work_root))


def cleanup_scratch_dir(scratch: Path) -> None:
    """Remove transient channel WAVs and any downloaded remote source copy."""
    shutil.rmtree(scratch, ignore_errors=True)
    try:
        scratch.parent.rmdir()
    except OSError:
        # Other workers can still be using .work, or it may not be empty.
        pass


def validate_call(call: Call, media_root: Path, source: Path | None = None) -> None:
    """Validate audio duration from a local original or temporary remote copy."""
    scratch: Path | None = None
    try:
        if source is None:
            scratch = create_scratch_dir(media_root, f"validate-{call.id}")
            source = storage.materialize(call.audio_path, media_root, scratch)
        if not source.is_file():
            raise FileNotFoundError(f"Recording is missing: {source}")
        duration = ffprobe_duration(source)
        if duration is None:
            raise ValueError("ffprobe could not read recording duration")
        # Playback and timeline calculations must use the inspected recording duration,
        # not potentially offset source metadata timestamps or a generic manifest guess.
        call.duration_seconds = duration
        call.processing_status = "VALIDATED"
    finally:
        if scratch is not None:
            cleanup_scratch_dir(scratch)


_whisper_model = None


def transcribe_channel(audio: Path, channel: int, output: Path) -> list[tuple[int, int, str, float | None]]:
    """Split a known stereo channel and transcribe it. Attribution is never inferred."""
    # `-map_channel` was removed in modern FFmpeg; pan explicitly selects the
    # known source channel while preserving deterministic source attribution.
    subprocess.run(
        [ffmpeg_binary(), "-nostdin", "-y", "-i", str(audio), "-map", "0:a:0", "-af", f"pan=mono|c0=c{channel}", "-ar", "16000", "-ac", "1", str(output)],
        check=True, capture_output=True,
    )
    global _whisper_model
    if _whisper_model is None:
        hf_home = settings.whisper_download_root.parent / "huggingface"
        os.environ.setdefault("HF_HOME", str(hf_home))
        os.environ.setdefault("HF_HUB_CACHE", str(hf_home / "hub"))
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(
            settings.whisper_model,
            compute_type=settings.whisper_compute_type,
            download_root=str(settings.whisper_download_root),
        )
    stream, _info = _whisper_model.transcribe(str(output), vad_filter=True, beam_size=5)
    segments: list[tuple[int, int, str, float | None]] = []
    for item in stream:
        text = item.text.strip()
        if text:
            segments.append((int(item.start * 1000), int(item.end * 1000), text, getattr(item, "avg_logprob", None)))
    return segments


def create_evidence(
    db: Session, call: Call, segments: dict[int, TranscriptSegment], analysis_type: str, claim: str, citation: EvidencePointer | None
) -> Evidence | None:
    valid, note = pointer_is_valid(citation, segments)
    if not valid or citation is None:
        return None
    segment = segments[citation.segment_id]
    evidence = Evidence(
        call_id=call.id, analysis_type=analysis_type, claim=claim, start_ms=segment.start_ms, end_ms=segment.end_ms,
        speaker=segment.speaker, quote=citation.quote, transcript_segment_id=segment.id, validated=True, validation_note=note,
    )
    db.add(evidence)
    db.flush()
    return evidence


def clear_analysis(db: Session, call: Call) -> None:
    # ``call_analyses.mood_shift_event_id`` references ``mood_events``.  Delete
    # the analysis row before its selected mood event so this works with real
    # PostgreSQL foreign-key enforcement (SQLite tests do not enable it by
    # default).
    db.query(AttentionContribution).filter_by(call_id=call.id).delete()
    if call.analysis:
        db.delete(call.analysis)
        db.flush()
    db.query(MoodEvent).filter_by(call_id=call.id).delete()
    db.query(Topic).filter_by(call_id=call.id).delete()
    db.query(Evidence).filter_by(call_id=call.id).delete()
    db.flush()


def persist_analysis(db: Session, call: Call, candidate: AnalysisCandidate, model_name: str | None) -> None:
    segments = {segment.id: segment for segment in call.transcript_segments}
    clear_analysis(db, call)
    intent_evidence = create_evidence(db, call, segments, "intent", candidate.intent_description or "", candidate.intent_evidence)
    resolution_evidence = create_evidence(db, call, segments, "resolution", candidate.resolution_status, candidate.resolution_evidence)
    summary_evidence = create_evidence(db, call, segments, "summary", candidate.summary or "", candidate.summary_evidence)
    analysis = CallAnalysis(
        call_id=call.id,
        intent_category=candidate.intent_category if intent_evidence else None,
        intent_description=candidate.intent_description if intent_evidence else None,
        intent_confidence=candidate.intent_confidence if intent_evidence else None,
        resolution_status=candidate.resolution_status if resolution_evidence else "UNKNOWN",
        summary=candidate.summary if summary_evidence else None,
        model_name=model_name,
    )
    db.add(analysis)
    db.flush()

    mood_rows: list[MoodEvent] = []
    for event in candidate.mood_events:
        citation = EvidencePointer(segment_id=event.segment_id, quote=event.quote)
        evidence = create_evidence(db, call, segments, "mood", event.mood, citation)
        if evidence:
            mood = MoodEvent(call_id=call.id, timestamp_ms=evidence.start_ms, mood=event.mood, score=event.score, evidence_segment_id=evidence.transcript_segment_id)
            db.add(mood)
            mood_rows.append(mood)
    db.flush()
    mood_rows.sort(key=lambda item: item.timestamp_ms)
    for previous, current in zip(mood_rows, mood_rows[1:]):
        if previous.mood != current.mood:
            analysis.mood_shift_from, analysis.mood_shift_to, analysis.mood_shift_event_id = previous.mood, current.mood, current.id
            break

    total = 0
    for contribution in candidate.attention_contributions:
        if contribution.signal not in ATTENTION_WEIGHTS:
            continue
        evidence = create_evidence(db, call, segments, "attention", contribution.explanation, contribution.evidence)
        if evidence:
            points = ATTENTION_WEIGHTS[contribution.signal]
            db.add(AttentionContribution(call_id=call.id, signal=contribution.signal, points=points, explanation=contribution.explanation, evidence_id=evidence.id))
            total += points
    analysis.attention_score = min(100, total)
    analysis.attention_band = attention_band(analysis.attention_score)
    if candidate.intent_category and intent_evidence:
        db.add(Topic(call_id=call.id, topic=candidate.intent_category, confidence=candidate.intent_confidence))


def process_call(db: Session, call: Call, media_root: Path) -> None:
    """Process exactly one call. Completed calls are never recomputed by the API."""
    call_id = call.id
    scratch: Path | None = None
    call.attempt_count += 1
    call.processing_error = None
    try:
        # Analysis was committed before a previous worker stopped. Finalize the
        # durable result rather than paying for another model invocation.
        if call.processing_status == "ANALYZED" and call.analysis:
            call.processing_status = "READY"
            call.processed_at = call.processed_at or datetime.now(UTC).replace(tzinfo=None)
            db.commit()
            return
        if call.processing_status == "ANALYZED":
            # A status flag without a durable analysis is an interrupted or
            # manually repaired state.  Re-run analysis using the persisted
            # transcript rather than falsely publishing an empty result.
            call.processing_status = "TRANSCRIBED"

        if call.processing_status not in ("TRANSCRIBED", "ANALYZING") or not call.transcript_segments:
            scratch = create_scratch_dir(media_root, call.id)
            source = storage.materialize(call.audio_path, media_root, scratch)
            validate_call(call, media_root, source=source)
            call.processing_status = "TRANSCRIBING"
            db.commit()
            # Fixed source mapping: channel 0/left is agent; channel 1/right is customer.
            records = [("agent", *record) for record in transcribe_channel(source, 0, scratch / "agent.wav")]
            records.extend(("customer", *record) for record in transcribe_channel(source, 1, scratch / "customer.wav"))
            records.sort(key=lambda item: (item[1], item[2], item[0]))
            db.query(TranscriptSegment).filter_by(call_id=call.id).delete()
            for speaker, start_ms, end_ms, text, confidence in records:
                db.add(TranscriptSegment(call_id=call.id, speaker=speaker, start_ms=start_ms, end_ms=end_ms, text=text, confidence=confidence))
            db.flush()
            call.processing_status = "TRANSCRIBED"
            db.commit()

        call.processing_status = "ANALYZING"
        db.commit()
        db.refresh(call)
        transcript = list(call.transcript_segments)
        engine = get_analysis_engine()
        candidate = engine.analyse(transcript)
        candidate = validate_candidate_evidence(candidate, {segment.id: segment for segment in transcript}, engine)
        persist_analysis(db, call, candidate, settings.openai_model if engine.__class__.__name__ == "OpenAIAnalysisEngine" else "rules")
        call.processing_status = "ANALYZED"
        db.commit()
        call.processing_status = "READY"
        call.processed_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
    except Exception as exc:
        db.rollback()
        failed_call = db.get(Call, call_id)
        if failed_call:
            failed_call.processing_status = "FAILED"
            failed_call.processing_error = str(exc)[:4000]
            db.commit()
        raise
    finally:
        if scratch is not None:
            cleanup_scratch_dir(scratch)


def process_batch(
    db: Session,
    media_root: Path,
    limit: int | None = None,
    retry_failed: bool = False,
    call_ids: Iterable[str] | None = None,
) -> dict[str, int]:
    # All non-terminal states are resumable; the implementation skips already-persisted
    # transcript work when possible. FAILED records require an explicit retry command.
    statuses = ACTIVE_STATUSES + (("FAILED",) if retry_failed else ())
    query = db.query(Call).filter(Call.processing_status.in_(statuses)).order_by(Call.created_at)
    if call_ids is not None:
        selected_ids = list(call_ids)
        if not selected_ids:
            return {"processed": 0, "failed": 0}
        query = query.filter(Call.id.in_(selected_ids))
    if limit:
        query = query.limit(limit)
    summary = {"processed": 0, "failed": 0}
    for call in query.all():
        try:
            process_call(db, call, media_root)
            summary["processed"] += 1
        except Exception:
            summary["failed"] += 1
    return summary
