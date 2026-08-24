"""Evidence-first deterministic analysis. A finding is emitted only with a source turn."""
from .models import Turn

def evidence(turn: Turn) -> dict:
    return {"turn_id": turn.id, "start_ms": turn.start_ms, "end_ms": turn.end_ms, "quote": turn.text}

def first_matching(turns, words):
    return next((t for t in turns if any(w in t.text.lower() for w in words)), None)

def analyse(turns: list[Turn]) -> dict:
    customer = [t for t in turns if t.speaker == "customer"]
    all_text = " ".join(t.text for t in customer).lower()
    intent_terms = {"card": ["card", "declined"], "payment": ["payment", "transfer"], "fraud": ["fraud", "scam", "unauthorised"], "balance": ["balance", "statement"]}
    intent = next(((name, first_matching(customer, words)) for name, words in intent_terms.items() if first_matching(customer, words)), None)
    negative = first_matching(customer, ["angry", "frustrated", "unacceptable", "complaint", "terrible", "cancel"])
    positive = first_matching(customer, ["thank", "thanks", "great", "helpful"])
    unresolved = first_matching(customer, ["not resolved", "still", "doesn't work", "does not work", "again"])
    score = min(100, (50 if negative else 0) + (35 if unresolved else 0) + (15 if "fraud" in all_text else 0))
    summary_source = customer[0] if customer else None
    return {
      "intent": {"label": intent[0], "evidence": evidence(intent[1])} if intent else None,
      "mood": {"label": "negative", "evidence": evidence(negative), "shift": {"to": "positive", "evidence": evidence(positive)}} if negative else ({"label": "positive", "evidence": evidence(positive)} if positive else None),
      "resolution": {"label": "unresolved", "evidence": evidence(unresolved)} if unresolved else None,
      "summary": {"text": summary_source.text[:240], "evidence": evidence(summary_source)} if summary_source else None,
      "attention_score": score,
      "attention_evidence": [evidence(t) for t in (negative, unresolved) if t],
    }
