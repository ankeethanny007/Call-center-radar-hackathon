"""Persistent data model for the offline Call-Centre Radar processing pipeline."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    calls: Mapped[list["Call"]] = relationship(back_populates="customer")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    calls: Mapped[list["Call"]] = relationship(back_populates="agent")


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), index=True, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), index=True, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    audio_path: Mapped[str] = mapped_column(String(1024))
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # DISCOVERED, VALIDATED, TRANSCRIBING, TRANSCRIBED, ANALYZING, ANALYZED, READY, FAILED
    processing_status: Mapped[str] = mapped_column(String(32), default="DISCOVERED", index=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    customer: Mapped[Customer | None] = relationship(back_populates="calls")
    agent: Mapped[Agent | None] = relationship(back_populates="calls")
    transcript_segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="call", cascade="all, delete-orphan", order_by="TranscriptSegment.start_ms"
    )
    analysis: Mapped["CallAnalysis | None"] = relationship(back_populates="call", uselist=False, cascade="all, delete-orphan")
    evidence_items: Mapped[list["Evidence"]] = relationship(back_populates="call", cascade="all, delete-orphan")
    mood_events: Mapped[list["MoodEvent"]] = relationship(back_populates="call", cascade="all, delete-orphan")
    topics: Mapped[list["Topic"]] = relationship(back_populates="call", cascade="all, delete-orphan")
    attention_contributions: Mapped[list["AttentionContribution"]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    speaker: Mapped[str] = mapped_column(String(16))  # agent or customer, determined by source channel
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    call: Mapped[Call] = relationship(back_populates="transcript_segments")


class CallAnalysis(Base):
    __tablename__ = "call_analyses"

    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), primary_key=True)
    intent_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    intent_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    attention_score: Mapped[int] = mapped_column(Integer, default=0)
    attention_band: Mapped[str] = mapped_column(String(32), default="LOW")
    mood_shift_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mood_shift_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mood_shift_event_id: Mapped[int | None] = mapped_column(ForeignKey("mood_events.id", use_alter=True), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    call: Mapped[Call] = relationship(back_populates="analysis")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    analysis_type: Mapped[str] = mapped_column(String(64), index=True)
    claim: Mapped[str] = mapped_column(Text)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(16))
    quote: Mapped[str] = mapped_column(Text)
    transcript_segment_id: Mapped[int] = mapped_column(ForeignKey("transcript_segments.id"))
    validated: Mapped[bool] = mapped_column(default=False)
    validation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    call: Mapped[Call] = relationship(back_populates="evidence_items")
    transcript_segment: Mapped[TranscriptSegment] = relationship()


class MoodEvent(Base):
    __tablename__ = "mood_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    timestamp_ms: Mapped[int] = mapped_column(Integer)
    mood: Mapped[str] = mapped_column(String(32))
    score: Mapped[int] = mapped_column(Integer)  # 0 strongly negative; 100 strongly positive
    evidence_segment_id: Mapped[int] = mapped_column(ForeignKey("transcript_segments.id"))
    call: Mapped[Call] = relationship(back_populates="mood_events")
    evidence_segment: Mapped[TranscriptSegment] = relationship()


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    topic: Mapped[str] = mapped_column(String(128))
    confidence: Mapped[float] = mapped_column(Float)
    call: Mapped[Call] = relationship(back_populates="topics")


class AttentionContribution(Base):
    __tablename__ = "attention_contributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    signal: Mapped[str] = mapped_column(String(128))
    points: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id"), nullable=True)
    call: Mapped[Call] = relationship(back_populates="attention_contributions")
    evidence: Mapped[Evidence | None] = relationship()


# Backwards-compatible import name for early callers.
Turn = TranscriptSegment
