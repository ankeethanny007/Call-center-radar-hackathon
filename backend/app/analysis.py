"""Structured, evidence-first conversation intelligence.

The analysis engine may suggest claims, but only claims with valid transcript citations
are persisted. Rules provide an offline fallback for local development and tests.
"""
from __future__ import annotations

import json
import re
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import settings
from .models import TranscriptSegment

ISSUE_TAXONOMY = (
    "billing", "fraud", "card", "account", "login", "payment", "refund",
    "cash_withdrawal", "transfer", "fees", "complaint", "general_inquiry", "other",
)
MOODS = ("positive", "neutral", "confused", "concerned", "frustrated", "angry", "distressed", "satisfied")
# Mood labels are the evidenced judgments.  Their displayed numeric values are
# a fixed presentation scale, never an unverified model-generated sentiment
# score. This makes the timeline deterministic across re-analysis runs.
MOOD_SCORES = {
    "positive": 80,
    "neutral": 50,
    "confused": 40,
    "concerned": 35,
    "frustrated": 20,
    "angry": 10,
    "distressed": 5,
    "satisfied": 90,
}
RESOLUTIONS = ("RESOLVED", "PARTIALLY_RESOLVED", "UNRESOLVED", "UNKNOWN")
ATTENTION_WEIGHTS = {
    "highly_negative_customer": 25,
    "issue_unresolved": 40,
    "escalation_requested": 15,
    "persistent_negative_mood": 15,
    "repeated_question": 10,
    "repeat_caller": 10,
    "agent_unable_to_answer": 30,
    "serious_complaint": 20,
    "abnormal_handle_time": 10,
    "transaction_amount_requested": 35,
    "transaction_amount_mismatch": 50,
    "transaction_completion_unconfirmed": 40,
    "unprofessional_agent_conduct": 35,
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidencePointer(StrictModel):
    segment_id: int
    quote: str = Field(min_length=1)


class MoodCandidate(StrictModel):
    segment_id: int
    mood: str
    score: int = Field(ge=0, le=100)
    quote: str

    @field_validator("mood")
    @classmethod
    def mood_is_allowed(cls, value: str) -> str:
        return value if value in MOODS else "neutral"


class ScoreCandidate(StrictModel):
    signal: str
    points: int = Field(ge=0, le=100)
    explanation: str
    evidence: EvidencePointer | None = None


class AnalysisCandidate(StrictModel):
    intent_category: str | None = None
    intent_description: str | None = None
    intent_confidence: float = Field(default=0, ge=0, le=1)
    intent_evidence: EvidencePointer | None = None
    resolution_status: str = "UNKNOWN"
    resolution_evidence: EvidencePointer | None = None
    summary: str | None = None
    summary_evidence: EvidencePointer | None = None
    mood_events: list[MoodCandidate] = Field(default_factory=list)
    attention_contributions: list[ScoreCandidate] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)

    @field_validator("intent_category")
    @classmethod
    def taxonomy_is_controlled(cls, value: str | None) -> str | None:
        return value if value in ISSUE_TAXONOMY else None

    @field_validator("resolution_status")
    @classmethod
    def resolution_is_allowed(cls, value: str) -> str:
        return value if value in RESOLUTIONS else "UNKNOWN"

    @field_validator("summary")
    @classmethod
    def summary_is_short(cls, value: str | None) -> str | None:
        return " ".join(value.split()[:40]) if value else value


class EvidenceValidationItem(StrictModel):
    claim_key: str
    supported: bool


class EvidenceValidationResult(StrictModel):
    items: list[EvidenceValidationItem]


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def openai_strict_schema(schema: object) -> object:
    """Adapt Pydantic JSON Schema to OpenAI Structured Outputs strict requirements."""
    if isinstance(schema, list):
        return [openai_strict_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key: openai_strict_schema(value) for key, value in schema.items()}
    properties = result.get("properties")
    if isinstance(properties, dict):
        result["additionalProperties"] = False
        result["required"] = list(properties.keys())
    return result


def pointer_is_valid(pointer: EvidencePointer | None, segments: dict[int, TranscriptSegment]) -> tuple[bool, str]:
    if pointer is None:
        return False, "Missing evidence pointer"
    segment = segments.get(pointer.segment_id)
    if segment is None:
        return False, "Referenced transcript segment does not exist"
    if normalize(pointer.quote) not in normalize(segment.text):
        return False, "Quoted evidence is not present in the referenced transcript segment"
    return True, "Validated transcript citation"


def word_limited(text: str, max_words: int = 40) -> str:
    return " ".join(text.split()[:max_words])


SUMMARY_INTENTS = {
    "account": "check their account balance",
    "transfer": "transfer money between accounts",
    "payment": "make or discuss a payment",
    "billing": "discuss a billing concern",
    "fraud": "report a potentially fraudulent transaction",
    "card": "get help with a bank card",
    "login": "get help accessing their account",
    "refund": "request or discuss a refund",
    "cash_withdrawal": "discuss a cash withdrawal",
    "fees": "discuss account fees",
    "complaint": "raise a service complaint",
    "general_inquiry": "make a general banking enquiry",
    "other": "request banking assistance",
}

SUMMARY_ISSUES = {
    "transaction_amount_mismatch": "a transaction amount mismatch",
    "transaction_completion_unconfirmed": "an unconfirmed transaction outcome",
    "unprofessional_agent_conduct": "inappropriate agent conduct",
    "highly_negative_customer": "strong customer dissatisfaction",
    "issue_unresolved": "an unresolved request",
    "escalation_requested": "a customer escalation request",
    "persistent_negative_mood": "persistent negative customer sentiment",
    "repeated_question": "repeated customer information",
    "repeat_caller": "repeat customer contact",
    "agent_unable_to_answer": "an unanswered customer request",
    "serious_complaint": "a serious customer complaint",
    "abnormal_handle_time": "a reported excessive wait",
}


def generated_summary(candidate: AnalysisCandidate, agent_name: str | None = None) -> tuple[str | None, EvidencePointer | None]:
    """Build a concise narrative only from findings that survived evidence validation."""
    source = candidate.intent_evidence or candidate.resolution_evidence or candidate.summary_evidence
    if source is None:
        source = next((item.evidence for item in candidate.attention_contributions if item.evidence), None)
    if source is None:
        return None, None

    purpose = SUMMARY_INTENTS.get(candidate.intent_category or "", "request banking assistance")
    summary = f"Customer called to {purpose}."
    agent = agent_name.strip() if agent_name and agent_name.strip() else "The agent"
    issues = list(dict.fromkeys(
        SUMMARY_ISSUES[item.signal]
        for item in candidate.attention_contributions
        if item.signal in SUMMARY_ISSUES
    ))

    if candidate.resolution_status == "RESOLVED":
        summary += f" {agent} resolved the request"
        summary += "." if issues else " without any issues."
    elif candidate.resolution_status == "PARTIALLY_RESOLVED":
        summary += f" {agent} partially resolved the request."
    elif candidate.resolution_status == "UNRESOLVED":
        summary += f" {agent} did not resolve the request."
    else:
        summary += " The outcome was not confirmed."

    if issues:
        summary += f" Manager review is recommended because of {', '.join(issues[:2])}."
    return word_limited(summary), source


def first_match(segments: Iterable[TranscriptSegment], terms: tuple[str, ...]) -> TranscriptSegment | None:
    return next((segment for segment in segments if any(term in normalize(segment.text) for term in terms)), None)


def pointer(segment: TranscriptSegment | None) -> EvidencePointer | None:
    return EvidencePointer(segment_id=segment.id, quote=segment.text) if segment else None


def stated_amount(segment: TranscriptSegment) -> int | None:
    match = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", segment.text)
    return round(float(match.group(1)) * 100) if match else None


class RuleAnalysisEngine:
    """Conservative fallback. It omits a claim rather than making an unsupported guess."""

    taxonomy_terms = {
        "fraud": ("fraud", "scam", "unrecognized", "unfamiliar", "unauthorised", "unauthorized"),
        "card": ("card", "declined", "pin"),
        "billing": ("bill", "billing", "charged", "charge"),
        "payment": ("payment", "pay ", "paid"),
        "refund": ("refund", "refunded"),
        "cash_withdrawal": ("cash withdrawal", "atm", "cash machine"),
        "transfer": ("transfer", "beneficiary", "wire"),
        "fees": ("fee", "fees", "charge"),
        "login": ("login", "log in", "password", "sign in"),
        "account": ("account", "balance", "statement"),
        "complaint": ("complaint", "complain", "unacceptable"),
        "general_inquiry": ("schedule an appointment", "appointment", "opening hours", "branch hours"),
    }

    def analyse(self, segments: list[TranscriptSegment], repeat_call_count: int = 0, duration_seconds: float | None = None) -> AnalysisCandidate:
        customers = [item for item in segments if item.speaker == "customer"]
        agents = [item for item in segments if item.speaker == "agent"]
        candidate = AnalysisCandidate()
        for category, terms in self.taxonomy_terms.items():
            found = first_match(customers, terms)
            if found:
                candidate.intent_category = category
                candidate.intent_description = word_limited(found.text)
                candidate.intent_confidence = 0.65
                candidate.intent_evidence = pointer(found)
                candidate.topics = [category]
                break

        unresolved = first_match(customers, ("not resolved", "nothing you can do", "still doesn't work", "still does not work", "still not", "again"))
        resolved = first_match(customers, ("that resolves", "that solved", "all sorted", "all set"))
        if unresolved:
            candidate.resolution_status, candidate.resolution_evidence = "UNRESOLVED", pointer(unresolved)
        elif resolved:
            candidate.resolution_status, candidate.resolution_evidence = "RESOLVED", pointer(resolved)

        source = customers[0] if customers else (agents[0] if agents else None)
        if source:
            candidate.summary, candidate.summary_evidence = word_limited(source.text), pointer(source)

        negative = first_match(customers, ("angry", "frustrated", "unacceptable", "terrible", "complaint", "ridiculous"))
        persistent_negative = first_match(customers, ("still frustrated", "still angry", "still upset", "still unacceptable", "still disappointed"))
        concerned = first_match(customers, ("worried", "concerned", "don't recognize", "do not recognize", "confused"))
        positive = first_match(customers, ("very helpful", "that was helpful", "appreciate your help", "great service", "excellent", "perfect"))
        if concerned:
            candidate.mood_events.append(MoodCandidate(segment_id=concerned.id, mood="concerned", score=35, quote=concerned.text))
        if negative:
            candidate.mood_events.append(MoodCandidate(segment_id=negative.id, mood="frustrated", score=20, quote=negative.text))
        if positive:
            candidate.mood_events.append(MoodCandidate(segment_id=positive.id, mood="satisfied", score=80, quote=positive.text))

        requested_amount = next(((item, stated_amount(item)) for item in customers if stated_amount(item) is not None), None)
        confirmed_amount = next(
            (
                (item, stated_amount(item))
                for item in agents
                if stated_amount(item) is not None
                and any(term in normalize(item.text) for term in ("transferred", "transfer", "send your payment", "paid"))
            ),
            None,
        )
        if requested_amount and confirmed_amount and requested_amount[1] != confirmed_amount[1]:
            request_segment, request_cents = requested_amount
            confirmation_segment, confirmation_cents = confirmed_amount
            candidate.attention_contributions.extend(
                (
                    ScoreCandidate(
                        signal="transaction_amount_requested",
                        points=ATTENTION_WEIGHTS["transaction_amount_requested"],
                        explanation=f"Customer requested a transaction amount of ${request_cents / 100:g}.",
                        evidence=pointer(request_segment),
                    ),
                    ScoreCandidate(
                        signal="transaction_amount_mismatch",
                        points=ATTENTION_WEIGHTS["transaction_amount_mismatch"],
                        explanation=f"Agent confirmed a different transaction amount of ${confirmation_cents / 100:g}.",
                        evidence=pointer(confirmation_segment),
                    ),
                )
            )
        elif requested_amount and confirmed_amount and requested_amount[1] == confirmed_amount[1]:
            confirmation_segment, _confirmation_cents = confirmed_amount
            candidate.resolution_status = "RESOLVED"
            candidate.resolution_evidence = pointer(confirmation_segment)

        balance_provided = first_match(agents, ("balance is", "account balance is"))
        if candidate.intent_category == "account" and balance_provided and not unresolved:
            candidate.resolution_status = "RESOLVED"
            candidate.resolution_evidence = pointer(balance_provided)

        escalation = first_match(customers, ("manager", "supervisor", "escalate", "complaint"))
        repeat_question = first_match(customers, ("already told", "already explained", "repeat myself", "third time"))
        # A source name by itself is not sufficient evidence for a manager-facing score.
        # This signal is emitted only when the caller explicitly states that this is a
        # repeat contact, so it remains directly seekable in the current recording.
        repeat_caller = first_match(customers, ("called before", "called previously", "called already", "second time calling", "third time calling", "fourth time calling"))
        # Do not infer this from the measured recording duration. It is only included
        # when a caller's own words substantively report an abnormal wait/handling time.
        abnormal_handle_time = first_match(customers, ("been on hold", "waiting for an hour", "waiting 30 minutes", "waiting thirty minutes", "long wait", "waiting so long"))
        unable = first_match(agents, ("can't", "cannot", "unable", "don't know", "do not know"))
        if negative:
            candidate.attention_contributions.append(ScoreCandidate(signal="highly_negative_customer", points=25, explanation="Customer expressed strong negative sentiment.", evidence=pointer(negative)))
        if unresolved:
            candidate.attention_contributions.append(ScoreCandidate(signal="issue_unresolved", points=ATTENTION_WEIGHTS["issue_unresolved"], explanation="Customer explicitly indicated the issue remained unresolved.", evidence=pointer(unresolved)))
        if escalation:
            candidate.attention_contributions.append(ScoreCandidate(signal="escalation_requested", points=15, explanation="Customer requested escalation or a manager.", evidence=pointer(escalation)))
        if repeat_question:
            candidate.attention_contributions.append(ScoreCandidate(signal="repeated_question", points=10, explanation="Customer indicated they had to repeat information.", evidence=pointer(repeat_question)))
        if repeat_caller:
            candidate.attention_contributions.append(ScoreCandidate(signal="repeat_caller", points=10, explanation="Customer explicitly said this was a repeat contact.", evidence=pointer(repeat_caller)))
        if unable and candidate.resolution_status != "RESOLVED":
            candidate.attention_contributions.append(ScoreCandidate(signal="agent_unable_to_answer", points=ATTENTION_WEIGHTS["agent_unable_to_answer"], explanation="Agent indicated they could not provide an answer.", evidence=pointer(unable)))
        if negative and escalation:
            candidate.attention_contributions.append(ScoreCandidate(signal="serious_complaint", points=20, explanation="Customer made a serious complaint or escalation request.", evidence=pointer(escalation)))
        if persistent_negative:
            candidate.attention_contributions.append(ScoreCandidate(signal="persistent_negative_mood", points=15, explanation="Customer explicitly described persistent negative sentiment.", evidence=pointer(persistent_negative)))
        if abnormal_handle_time:
            candidate.attention_contributions.append(ScoreCandidate(signal="abnormal_handle_time", points=10, explanation="Customer explicitly reported a prolonged wait or handling time.", evidence=pointer(abnormal_handle_time)))
        inappropriate_laughter = first_match(agents, ("[laughter]", "[laughs]", "[chuckles]"))
        if inappropriate_laughter:
            candidate.attention_contributions.append(
                ScoreCandidate(
                    signal="unprofessional_agent_conduct",
                    points=ATTENTION_WEIGHTS["unprofessional_agent_conduct"],
                    explanation="Agent laughed at the end of the customer interaction; manager review is recommended.",
                    evidence=pointer(inappropriate_laughter),
                )
            )
        return candidate


class OpenAIAnalysisEngine:
    """Uses Responses API structured output, then validates every citation locally."""

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when ANALYSIS_PROVIDER=openai")
        from openai import OpenAI
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout_seconds,
            max_retries=1,
        )

    def analyse(self, segments: list[TranscriptSegment], repeat_call_count: int = 0, duration_seconds: float | None = None) -> AnalysisCandidate:
        transcript = "\n".join(
            f"[{segment.id}] {segment.start_ms}ms {segment.speaker.upper()}: {segment.text}" for segment in segments
        )
        instructions = """You are an evidence-first call-centre analyst. Analyze only the transcript supplied.
Every non-null field must cite an existing transcript segment and an exact quote from that segment.
Use only this issue taxonomy: billing, fraud, card, account, login, payment, refund, cash_withdrawal, transfer, fees, complaint, general_inquiry, other.
Use only RESOLVED, PARTIALLY_RESOLVED, UNRESOLVED, UNKNOWN for resolution.
Use only positive, neutral, confused, concerned, frustrated, angry, distressed, satisfied for moods.
Do not infer missing facts. Keep summary to 40 words maximum. Use only these attention signal names with their fixed weights: highly_negative_customer (25), issue_unresolved (40), escalation_requested (15), persistent_negative_mood (15), repeated_question (10), repeat_caller (10), agent_unable_to_answer (30), serious_complaint (20), abnormal_handle_time (10), transaction_completion_unconfirmed (40). A repeat_caller signal requires the customer to explicitly say this is a repeat contact. An abnormal_handle_time signal requires the customer to explicitly report a prolonged wait or handling time; never infer either signal from metadata. Every contribution needs a directly supporting citation."""
        payload = f"TRANSCRIPT:\n{transcript}"
        response = self.client.responses.create(
            model=settings.openai_model,
            instructions=instructions,
            input=payload,
            text={"format": {"type": "json_schema", "name": "call_analysis", "strict": True, "schema": openai_strict_schema(AnalysisCandidate.model_json_schema())}},
            store=False,
        )
        return AnalysisCandidate.model_validate(json.loads(response.output_text))

    def validate_evidence(self, claims: list[dict[str, str]]) -> dict[str, bool]:
        """A separate semantic gate: citations must substantively support each claim."""
        if not claims:
            return {}
        response = self.client.responses.create(
            model=settings.openai_model,
            instructions="""You are an evidence validator. For each claim, decide whether the quoted transcript text directly supports it.
Do not accept claims based only on a related topic or similar wording. For a summary, a concise faithful paraphrase of the cited quote is supported. Return one decision per claim key.""",
            input=json.dumps(claims),
            text={"format": {"type": "json_schema", "name": "evidence_validation", "strict": True, "schema": openai_strict_schema(EvidenceValidationResult.model_json_schema())}},
            store=False,
        )
        result = EvidenceValidationResult.model_validate(json.loads(response.output_text))
        return {item.claim_key: item.supported for item in result.items}


def validate_candidate_evidence(
    candidate: AnalysisCandidate, segments: dict[int, TranscriptSegment], engine: RuleAnalysisEngine | OpenAIAnalysisEngine
) -> AnalysisCandidate:
    """Reject unsupported claims before persistence; no valid citation means no returned claim."""
    unconfirmed_transaction_evidence: EvidencePointer | None = None
    if candidate.resolution_status == "RESOLVED" and candidate.resolution_evidence:
        resolution_quote = normalize(candidate.resolution_evidence.quote).rstrip(".!?")
        generic_closings = (
            "no, that will be it",
            "no that will be it",
            "no, that'll be it",
            "no that'll be it",
            "nothing else",
            "thank you",
            "thanks",
        )
        if any(resolution_quote == closing for closing in generic_closings):
            # A caller ending the conversation can evidence their closing mood,
            # but cannot prove that the requested transaction or action occurred.
            resolution_segment = segments.get(candidate.resolution_evidence.segment_id)
            closing_start = resolution_segment.start_ms if resolution_segment else max((item.start_ms for item in segments.values()), default=0)
            candidate.resolution_status, candidate.resolution_evidence = "UNKNOWN", None
            if candidate.intent_category in {"payment", "transfer", "refund", "cash_withdrawal"}:
                premature_close = next(
                    (
                        item
                        for item in sorted(segments.values(), key=lambda value: value.start_ms, reverse=True)
                        if item.speaker == "agent" and item.start_ms <= closing_start and "anything else" in normalize(item.text)
                    ),
                    None,
                )
                if premature_close:
                    unconfirmed_transaction_evidence = pointer(premature_close)

    candidate.attention_contributions = [
        item
        for item in candidate.attention_contributions
        if not (
            item.signal in {"issue_unresolved", "agent_unable_to_answer"}
            and any(term in normalize(item.explanation) for term in ("issue was resolved", "successfully resolved", "request was completed"))
            and "not resolved" not in normalize(item.explanation)
        )
    ]
    if candidate.resolution_status == "RESOLVED":
        # These signals describe failure to answer/resolve. They are logically
        # incompatible with an evidenced resolved outcome, even if a model emits
        # them with prose that actually praises the agent.
        candidate.attention_contributions = [
            item
            for item in candidate.attention_contributions
            if item.signal not in {"issue_unresolved", "agent_unable_to_answer", "transaction_completion_unconfirmed"}
        ]
    customer_segments = sorted((segment for segment in segments.values() if segment.speaker == "customer"), key=lambda item: item.start_ms)
    if customer_segments:
        # Search the final customer turns because channel-level word timestamps can
        # put a short farewell after the substantive closing statement. A grateful
        # close or an explicit statement that no more help is needed is direct
        # evidence for terminal satisfaction. It does not imply issue resolution.
        explicit_praise = next(
            (segment for segment in reversed(customer_segments[-3:]) if any(term in normalize(segment.text) for term in ("very helpful", "appreciate your help", "great service", "excellent", "perfect"))),
            None,
        )
        closing_customer = explicit_praise or next(
            (
                segment
                for segment in reversed(customer_segments[-3:])
                if any(
                    term in normalize(segment.text)
                    for term in (
                        "thank you",
                        "thanks",
                        "all set",
                        "that's all",
                        "that is all",
                        "that'll be all",
                        "that will be all",
                    )
                )
            ),
            None,
        )
        integrity_risk = any(item.signal in {"transaction_amount_requested", "transaction_amount_mismatch"} for item in candidate.attention_contributions)
        if closing_customer and (explicit_praise or (candidate.resolution_status == "RESOLVED" and not integrity_risk)):
            candidate.mood_events = [event for event in candidate.mood_events if event.segment_id != closing_customer.id]
            candidate.mood_events.append(
                MoodCandidate(
                    segment_id=closing_customer.id,
                    mood="satisfied",
                    score=MOOD_SCORES["satisfied"],
                    quote=closing_customer.text,
                )
            )
    entries: list[tuple[str, str, EvidencePointer]] = []
    if candidate.intent_category and candidate.intent_description and candidate.intent_evidence:
        # The controlled category is a manager-facing judgment too. Validate it with
        # the detail rather than merely checking that the free-text description fits.
        entries.append(("intent", f"{candidate.intent_category}: {candidate.intent_description}", candidate.intent_evidence))
    if candidate.resolution_status != "UNKNOWN" and candidate.resolution_evidence:
        entries.append(("resolution", candidate.resolution_status, candidate.resolution_evidence))
    if candidate.summary and candidate.summary_evidence:
        entries.append(("summary", candidate.summary, candidate.summary_evidence))
    for index, mood in enumerate(candidate.mood_events):
        entries.append((f"mood:{index}", mood.mood, EvidencePointer(segment_id=mood.segment_id, quote=mood.quote)))
    for index, contribution in enumerate(candidate.attention_contributions):
        if contribution.evidence:
            # The fixed score signal—not just its prose explanation—must be supported
            # by the cited words before it can influence a manager-facing score.
            entries.append((f"attention:{index}", f"{contribution.signal}: {contribution.explanation}", contribution.evidence))

    allowed: dict[str, bool] = {}
    claims_for_model: list[dict[str, str]] = []
    for key, claim, citation in entries:
        local_valid, _note = pointer_is_valid(citation, segments)
        allowed[key] = local_valid
        if local_valid and isinstance(engine, OpenAIAnalysisEngine) and settings.validate_evidence_with_llm:
            segment = segments[citation.segment_id]
            claims_for_model.append({"claim_key": key, "claim": claim, "speaker": segment.speaker, "quote": citation.quote})
    if claims_for_model:
        try:
            semantic = engine.validate_evidence(claims_for_model)
            for key in [item["claim_key"] for item in claims_for_model]:
                allowed[key] = allowed[key] and semantic.get(key, False)
        except Exception:
            # Fail closed: evidence that cannot be validated by the configured validator is omitted.
            for item in claims_for_model:
                allowed[item["claim_key"]] = False

    if not allowed.get("intent", False):
        candidate.intent_category = candidate.intent_description = None
        candidate.intent_confidence = 0
        candidate.intent_evidence = None
        candidate.topics = []
    if candidate.resolution_status != "UNKNOWN" and not allowed.get("resolution", False):
        candidate.resolution_status, candidate.resolution_evidence = "UNKNOWN", None
    if candidate.summary and not allowed.get("summary", False):
        # Preserve the required <=40-word summary using a directly cited source excerpt
        # rather than retaining a potentially unsupported generated paraphrase.
        source = segments.get(candidate.summary_evidence.segment_id) if candidate.summary_evidence else next(iter(segments.values()), None)
        candidate.summary = word_limited(source.text) if source else None
        candidate.summary_evidence = pointer(source) if source else None
    candidate.mood_events = [event for index, event in enumerate(candidate.mood_events) if allowed.get(f"mood:{index}", False)]
    for event in candidate.mood_events:
        event.score = MOOD_SCORES[event.mood]
    selected_signals: set[str] = set()
    safe_contributions: list[ScoreCandidate] = []
    for index, item in enumerate(candidate.attention_contributions):
        if not allowed.get(f"attention:{index}", False) or item.signal not in ATTENTION_WEIGHTS or item.signal in selected_signals:
            continue
        item.points = ATTENTION_WEIGHTS[item.signal]
        selected_signals.add(item.signal)
        safe_contributions.append(item)
    candidate.attention_contributions = safe_contributions
    if unconfirmed_transaction_evidence and "transaction_completion_unconfirmed" not in selected_signals:
        candidate.attention_contributions.append(
            ScoreCandidate(
                signal="transaction_completion_unconfirmed",
                points=ATTENTION_WEIGHTS["transaction_completion_unconfirmed"],
                explanation="The agent moved to close the call without confirming that the requested transaction was completed.",
                evidence=unconfirmed_transaction_evidence,
            )
        )
    return candidate


def get_analysis_engine() -> RuleAnalysisEngine | OpenAIAnalysisEngine:
    if settings.analysis_provider.lower() == "rules":
        return RuleAnalysisEngine()
    try:
        return OpenAIAnalysisEngine()
    except Exception:
        # An API configuration outage must not discard a successfully transcribed call.
        return RuleAnalysisEngine()


def attention_band(score: int) -> str:
    if score >= 85: return "IMMEDIATE_ATTENTION"
    if score >= 70: return "CRITICAL"
    if score >= 50: return "HIGH"
    if score >= 30: return "MODERATE"
    return "LOW"
