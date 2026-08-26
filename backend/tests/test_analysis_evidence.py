from app.analysis import ATTENTION_WEIGHTS, MOOD_SCORES, MoodCandidate, RuleAnalysisEngine, validate_candidate_evidence
from app.pipeline import metadata_record, validate_metadata_shape
from app.models import TranscriptSegment


def segment(identifier: int, speaker: str, text: str, start_ms: int = 0) -> TranscriptSegment:
    return TranscriptSegment(id=identifier, call_id="test-call", speaker=speaker, start_ms=start_ms, end_ms=start_ms + 1000, text=text)


def test_verified_callradar_metadata_maps_to_display_identities() -> None:
    metadata = {
        "sid": "abc123", "session": "Little Harper Valley 1", "start_time_ms": 1_700_000_000_000,
        "end_time_ms": 1_700_000_060_000, "labels": {},
        "agent": {"metadata": {"agent_name": "Alex"}},
        "caller": {"metadata": {"first and last name": "Sam Smith"}},
    }
    assert validate_metadata_shape("abc123", metadata) is None
    row = metadata_record("abc123", "callradar-data/audio/abc123.mp3", metadata)
    assert row["agent_name"] == "Alex"
    assert row["customer_name"] == "Sam Smith"
    assert row["agent_id"].startswith("agent-")
    assert row["customer_id"].startswith("customer-")


def test_invalid_source_metadata_is_rejected() -> None:
    assert "sid" in validate_metadata_shape("abc", {"session": "x"})


def test_rule_analysis_uses_only_citable_evidence_and_fixed_score_weights() -> None:
    segments = [
        segment(1, "customer", "I am frustrated and this is unacceptable.", 1_000),
        segment(2, "customer", "This is still not resolved. I need a supervisor.", 2_000),
        segment(3, "agent", "I cannot make that decision.", 3_000),
    ]
    candidate = RuleAnalysisEngine().analyse(segments, repeat_call_count=8, duration_seconds=3_600)
    candidate = validate_candidate_evidence(candidate, {item.id: item for item in segments}, RuleAnalysisEngine())
    signals = {item.signal: item.points for item in candidate.attention_contributions}
    assert signals["highly_negative_customer"] == ATTENTION_WEIGHTS["highly_negative_customer"]
    assert signals["issue_unresolved"] == ATTENTION_WEIGHTS["issue_unresolved"]
    assert "repeat_caller" not in signals
    assert "abnormal_handle_time" not in signals
    assert all(item.evidence and item.evidence.quote in {segment.text for segment in segments} for item in candidate.attention_contributions)


def test_summary_is_hard_limited_to_forty_words() -> None:
    text = " ".join(f"word{index}" for index in range(60))
    candidate = RuleAnalysisEngine().analyse([segment(1, "customer", text)])
    assert candidate.summary is not None
    assert len(candidate.summary.split()) == 40


def test_repeat_contact_and_wait_signals_require_customer_words() -> None:
    segments = [
        segment(1, "customer", "This is my second time calling. I have been on hold for an hour.", 1_000),
    ]
    candidate = RuleAnalysisEngine().analyse(segments)
    candidate = validate_candidate_evidence(candidate, {item.id: item for item in segments}, RuleAnalysisEngine())
    signals = {item.signal: item.points for item in candidate.attention_contributions}
    assert signals["repeat_caller"] == ATTENTION_WEIGHTS["repeat_caller"]
    assert signals["abnormal_handle_time"] == ATTENTION_WEIGHTS["abnormal_handle_time"]


def test_mood_scores_are_fixed_after_evidence_validation() -> None:
    source = segment(1, "customer", "I am frustrated about this.")
    candidate = RuleAnalysisEngine().analyse([source])
    candidate.mood_events = [MoodCandidate(segment_id=1, mood="frustrated", score=99, quote=source.text)]

    validated = validate_candidate_evidence(candidate, {source.id: source}, RuleAnalysisEngine())

    assert validated.mood_events[0].score == MOOD_SCORES["frustrated"]


def test_grateful_final_customer_turn_is_evidenced_as_satisfied() -> None:
    segments = [
        segment(1, "customer", "I am confused about the appointment.", 1_000),
        segment(2, "customer", "Thank you. Bye.", 8_000),
    ]
    candidate = RuleAnalysisEngine().analyse(segments)
    candidate.resolution_status = "RESOLVED"

    validated = validate_candidate_evidence(candidate, {item.id: item for item in segments}, RuleAnalysisEngine())

    final_mood = sorted(validated.mood_events, key=lambda item: item.segment_id)[-1]
    assert final_mood.segment_id == 2
    assert final_mood.mood == "satisfied"
    assert final_mood.quote == "Thank you. Bye."


def test_explicit_no_more_help_before_farewell_is_satisfied() -> None:
    segments = [
        segment(1, "customer", "Well, no, that's all for today.", 30_000),
        segment(2, "customer", "You too.", 40_000),
        segment(3, "customer", "Bye-bye.", 45_000),
    ]
    candidate = RuleAnalysisEngine().analyse(segments)
    candidate.resolution_status = "RESOLVED"

    validated = validate_candidate_evidence(candidate, {item.id: item for item in segments}, RuleAnalysisEngine())

    final_mood = sorted(validated.mood_events, key=lambda item: item.segment_id)[-1]
    assert final_mood.segment_id == 1
    assert final_mood.mood == "satisfied"
    assert final_mood.quote == "Well, no, that's all for today."


def test_polite_close_does_not_mask_transaction_amount_mismatch() -> None:
    segments = [
        segment(1, "customer", "Transfer $86 from checking to savings.", 10_000),
        segment(2, "agent", "$26 has been transferred from checking to savings.", 20_000),
        segment(3, "customer", "No, that'll be it. Thank you.", 30_000),
    ]

    candidate = RuleAnalysisEngine().analyse(segments)
    validated = validate_candidate_evidence(candidate, {item.id: item for item in segments}, RuleAnalysisEngine())

    signals = {item.signal: item.points for item in validated.attention_contributions}
    assert signals["transaction_amount_requested"] == 35
    assert signals["transaction_amount_mismatch"] == 50
    assert not any(item.mood == "satisfied" for item in validated.mood_events)


def test_matching_transfer_amount_is_resolved_and_satisfied() -> None:
    segments = [
        segment(1, "customer", "Transfer $86 from checking to savings.", 10_000),
        segment(2, "agent", "$86 has been transferred from checking to savings.", 20_000),
        segment(3, "customer", "No, that'll be it. Thank you.", 30_000),
    ]

    candidate = RuleAnalysisEngine().analyse(segments)
    validated = validate_candidate_evidence(candidate, {item.id: item for item in segments}, RuleAnalysisEngine())

    assert validated.resolution_status == "RESOLVED"
    assert validated.resolution_evidence is not None
    assert not validated.attention_contributions
    assert validated.mood_events[-1].mood == "satisfied"


def test_customer_joke_is_not_frustration_but_agent_laughter_needs_review() -> None:
    segments = [
        segment(1, "customer", "I need to check my account balance.", 10_000),
        segment(2, "agent", "Your savings account balance is $65.", 20_000),
        segment(3, "customer", "Can you help me get more money?", 30_000),
        segment(6, "agent", "Unfortunately, I cannot do that.", 35_000),
        segment(4, "customer", "I appreciate your help checking my very low balance.", 40_000),
        segment(5, "agent", "[laughter]", 50_000),
    ]

    candidate = RuleAnalysisEngine().analyse(segments)
    validated = validate_candidate_evidence(candidate, {item.id: item for item in segments}, RuleAnalysisEngine())

    assert validated.resolution_status == "RESOLVED"
    assert validated.mood_events[-1].mood == "satisfied"
    assert not any(item.mood == "frustrated" for item in validated.mood_events)
    signals = {item.signal: item.points for item in validated.attention_contributions}
    assert signals == {"unprofessional_agent_conduct": 35}


def test_appointment_request_maps_to_general_inquiry() -> None:
    source = segment(1, "customer", "I would like to schedule an appointment.")

    candidate = RuleAnalysisEngine().analyse([source])

    assert candidate.intent_category == "general_inquiry"
    assert candidate.intent_evidence is not None
    assert candidate.intent_evidence.quote == source.text
