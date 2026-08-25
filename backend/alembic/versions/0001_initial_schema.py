"""Create the persistent Call-Centre Radar schema.

This migration is deliberately database-neutral: SQLite is supported for a
local smoke test and PostgreSQL/Supabase is the production target.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "calls",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("customer_id", sa.String(length=128), nullable=True),
        sa.Column("agent_id", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("audio_path", sa.String(length=1024), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calls_agent_id", "calls", ["agent_id"], unique=False)
    op.create_index("ix_calls_customer_id", "calls", ["customer_id"], unique=False)
    op.create_index("ix_calls_processing_status", "calls", ["processing_status"], unique=False)
    op.create_index("ix_calls_started_at", "calls", ["started_at"], unique=False)

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("speaker", sa.String(length=16), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transcript_segments_call_id", "transcript_segments", ["call_id"], unique=False)

    op.create_table(
        "mood_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("timestamp_ms", sa.Integer(), nullable=False),
        sa.Column("mood", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("evidence_segment_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"]),
        sa.ForeignKeyConstraint(["evidence_segment_id"], ["transcript_segments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mood_events_call_id", "mood_events", ["call_id"], unique=False)

    op.create_table(
        "call_analyses",
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("intent_category", sa.String(length=64), nullable=True),
        sa.Column("intent_description", sa.Text(), nullable=True),
        sa.Column("intent_confidence", sa.Float(), nullable=True),
        sa.Column("resolution_status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("attention_score", sa.Integer(), nullable=False),
        sa.Column("attention_band", sa.String(length=32), nullable=False),
        sa.Column("mood_shift_from", sa.String(length=32), nullable=True),
        sa.Column("mood_shift_to", sa.String(length=32), nullable=True),
        sa.Column("mood_shift_event_id", sa.Integer(), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"]),
        sa.ForeignKeyConstraint(["mood_shift_event_id"], ["mood_events.id"]),
        sa.PrimaryKeyConstraint("call_id"),
    )

    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("analysis_type", sa.String(length=64), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(length=16), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("transcript_segment_id", sa.Integer(), nullable=False),
        sa.Column("validated", sa.Boolean(), nullable=False),
        sa.Column("validation_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"]),
        sa.ForeignKeyConstraint(["transcript_segment_id"], ["transcript_segments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_analysis_type", "evidence", ["analysis_type"], unique=False)
    op.create_index("ix_evidence_call_id", "evidence", ["call_id"], unique=False)

    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_topics_call_id", "topics", ["call_id"], unique=False)

    op.create_table(
        "attention_contributions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("signal", sa.String(length=128), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"]),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attention_contributions_call_id", "attention_contributions", ["call_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_attention_contributions_call_id", table_name="attention_contributions")
    op.drop_table("attention_contributions")
    op.drop_index("ix_topics_call_id", table_name="topics")
    op.drop_table("topics")
    op.drop_index("ix_evidence_call_id", table_name="evidence")
    op.drop_index("ix_evidence_analysis_type", table_name="evidence")
    op.drop_table("evidence")
    op.drop_table("call_analyses")
    op.drop_index("ix_mood_events_call_id", table_name="mood_events")
    op.drop_table("mood_events")
    op.drop_index("ix_transcript_segments_call_id", table_name="transcript_segments")
    op.drop_table("transcript_segments")
    op.drop_index("ix_calls_started_at", table_name="calls")
    op.drop_index("ix_calls_processing_status", table_name="calls")
    op.drop_index("ix_calls_customer_id", table_name="calls")
    op.drop_index("ix_calls_agent_id", table_name="calls")
    op.drop_table("calls")
    op.drop_table("agents")
    op.drop_table("customers")
