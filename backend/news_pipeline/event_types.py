"""Cheap keyword classification of what KIND of event an article describes -
purely an organizational/debug label on the event (spec section 4's
event_type field), not an input to sentiment scoring itself. Checked
top-to-bottom; first match wins, so more specific categories are listed
before generic ones."""

EVENT_TYPE_KEYWORDS = [
    # High-impact, specific categories checked first so a fraud/bankruptcy/
    # rating/product-recall/court-ruling headline doesn't fall through to the
    # more generic REGULATORY/OTHER buckets below - these also drive the
    # high-impact LLM escalation gate (config.HIGH_IMPACT_EVENT_TYPES).
    ("FRAUD", ["fraud", "scam", "forgery", "embezzlement", "siphoning"]),
    ("BANKRUPTCY", ["bankruptcy", "insolvency", "insolvent", "liquidation", "debt default", "defaults on"]),
    ("CREDIT_RATING", ["credit rating", "rating downgrade", "rating upgrade", "downgraded to", "upgraded to", "crisil", "icra", "moody's", "fitch"]),
    ("PRODUCT_FAILURE", ["product recall", "recalls", "safety defect", "malfunction"]),
    ("LEGAL_RULING", ["court ruling", "tribunal", "verdict", "supreme court", "high court", "nclt", "sebi order"]),
    ("EARNINGS", ["profit", "results", "earnings", "quarterly", "q1 ", "q2 ", "q3 ", "q4 ", "revenue", "net income"]),
    ("GUIDANCE", ["guidance", "outlook", "forecast raised", "forecast cut"]),
    ("REGULATORY", ["probe", "investigation", "raid", "penalty", "fine", "sebi", "regulator", "compliance", "lawsuit", "litigation"]),
    ("MNA", ["acquisition", "acquires", "merger", "buyout", "takeover", "stake sale", "divest"]),
    ("CONTRACT_WIN", ["contract", "order", "deal", "wins", "bags", "secures"]),
    ("PRODUCT_LAUNCH", ["launches", "launch", "unveils", "introduces"]),
    ("LEADERSHIP", ["resign", "resignation", "steps down", "appoints", "appointment", " ceo ", " cfo ", " md "]),
    ("MACRO", ["rbi", "repo rate", "inflation", "gdp", "fiscal deficit", "union budget", "interest rate"]),
]


def classify_event_type(text: str) -> str:
    text_lc = f" {text.lower()} "
    for event_type, keywords in EVENT_TYPE_KEYWORDS:
        if any(kw in text_lc for kw in keywords):
            return event_type
    return "OTHER"
