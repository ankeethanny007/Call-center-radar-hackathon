from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    calls = relationship("Call", back_populates="customer")

class Call(Base):
    __tablename__ = "calls"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    audio_path: Mapped[str] = mapped_column(String)
    metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    customer = relationship("Customer", back_populates="calls")
    turns = relationship("Turn", back_populates="call", cascade="all, delete-orphan")
    analysis = relationship("Analysis", back_populates="call", uselist=False, cascade="all, delete-orphan")

class Turn(Base):
    __tablename__ = "turns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    speaker: Mapped[str] = mapped_column(String) # deterministic: agent=left, customer=right
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    call = relationship("Call", back_populates="turns")

class Analysis(Base):
    __tablename__ = "analyses"
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), primary_key=True)
    intent: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mood: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attention_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attention_evidence: Mapped[list] = mapped_column(JSON, default=list)
    call = relationship("Call", back_populates="analysis")
