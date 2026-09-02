"""Tier-0 (lexicon + rules) and Tier-2 (optional LLM) financial-sentiment
classifiers, behind one small swappable interface.

Why tiered (see plan / config.py for the numbers): Tier-0 is free and runs
everywhere, including the once-daily ~2,300-symbol scan. Tier-2 is reserved
for genuinely ambiguous headlines on low-volume, high-value call sites (a
single stock's detail page, IPO lookups) - never the daily scan, never the RSS
poller. FinBERT was evaluated and rejected for V1 (heavy new dependency,
unverified on this Python 3.14 venv, marginal edge over Tier-0 concentrated in
exactly the ambiguous cases Tier-2 already covers) - this ABC is exactly the
seam that would let it be dropped in later as a third tier with no rewrite.
"""
import re
from abc import ABC, abstractmethod

import requests

from . import config, lexicon

_WORD_RE = re.compile(r"[a-z_']+")


class SentimentClassifier(ABC):
    @abstractmethod
    def classify(self, text: str) -> dict:
        """Returns {score: float[-1,1], label: str, confidence: float[0,1],
        is_ambiguous: bool, trace: list[dict]}."""
        ...


def _build_phrase_table():
    """Multi-word lexicon phrases ("guidance cut", "market rises", ...) need
    to act as one unit for the negation/magnitude window logic below, so they
    get joined into a single underscore token before word-tokenizing. Sorted
    longest-first so "guidance cut" is substituted before a bare "guidance"
    (which isn't even in the lexicon, but the principle matters for phrases
    that do overlap)."""
    phrases = []
    for category, words in lexicon.CATEGORY_WORDS.items():
        for phrase in words:
            if " " in phrase:
                phrases.append((phrase, phrase.replace(" ", "_")))
    phrases.sort(key=lambda p: len(p[0]), reverse=True)
    return phrases


_PHRASE_TABLE = _build_phrase_table()

_WORD_TO_CATEGORY = {}
for _category, _words in lexicon.CATEGORY_WORDS.items():
    for _phrase in _words:
        _key = _phrase.replace(" ", "_") if " " in _phrase else _phrase
        _WORD_TO_CATEGORY[_key] = _category


def _join_multiword_phrases(text: str) -> str:
    for phrase, joined in _PHRASE_TABLE:
        text = re.sub(r"\b" + re.escape(phrase) + r"\b", joined, text)
    return text


def _split_clauses(text: str):
    """Splits on contrast connectors (but/however/although/...) so each side
    of a "profit rises but guidance cut" style sentence gets scored
    independently instead of netted together at the word level."""
    connector_pattern = r"\b(" + "|".join(re.escape(c) for c in lexicon.CONTRAST_CONNECTORS) + r")\b"
    parts = re.split(connector_pattern, text)
    clauses = [p for i, p in enumerate(parts) if i % 2 == 0 and p.strip()]
    had_contrast = len(parts) > 1
    return clauses if clauses else [text], had_contrast


def _score_clause(tokens: list[str]):
    raw_score = 0.0
    hits = []
    for i, token in enumerate(tokens):
        category = _WORD_TO_CATEGORY.get(token)
        if category is None:
            continue
        weight = lexicon.WEIGHTS[category]
        negated = False
        window_start = max(0, i - lexicon.NEGATION_WINDOW)
        if any(t in lexicon.NEGATION_WORDS for t in tokens[window_start:i]):
            weight = -weight * config.NEGATION_DAMPEN_FACTOR
            negated = True

        magnitude_multiplier = 1.0
        mag_window_start = max(0, i - lexicon.MAGNITUDE_WINDOW)
        for t in tokens[mag_window_start:i]:
            if t in lexicon.MAGNITUDE_UP:
                magnitude_multiplier = lexicon.MAGNITUDE_UP[t]
                break
            if t in lexicon.MAGNITUDE_DOWN:
                magnitude_multiplier = lexicon.MAGNITUDE_DOWN[t]
                break

        contribution = weight * magnitude_multiplier
        raw_score += contribution
        hits.append({
            "phrase": token.replace("_", " "), "category": category,
            "base_weight": lexicon.WEIGHTS[category], "negated": negated,
            "magnitude_multiplier": magnitude_multiplier, "contribution": round(contribution, 3),
        })
    return raw_score, hits


# Two clauses need at least this much raw magnitude, in opposite directions,
# before a contrast connector is treated as a genuine pos/neg conflict rather
# than filler ("... but that's expected").
_MIXED_MIN_CLAUSE_MAGNITUDE = 0.8
_NORMALIZATION_DIVISOR = 4.0  # ~2 strong-category hits saturates to +/-1.0


class LexiconSentimentClassifier(SentimentClassifier):
    """Rule-augmented financial lexicon: negation scope + contrast-clause
    splitting + magnitude modifiers on top of a weighted, categorized word
    list. Not real NLP, but a deliberate, explainable, zero-cost, zero-new-
    dependency upgrade from plain keyword counting - see the tradeoff writeup
    in the plan for why this, not FinBERT, is Tier 0."""

    def classify(self, text: str) -> dict:
        if not text or not text.strip():
            return {"score": 0.0, "label": "NEUTRAL", "confidence": 0.0, "is_ambiguous": False, "trace": []}

        normalized = _join_multiword_phrases(text.lower())
        clause_texts, had_contrast = _split_clauses(normalized)

        clause_results = []
        for clause_text in clause_texts:
            tokens = _WORD_RE.findall(clause_text)
            raw_score, hits = _score_clause(tokens)
            clause_results.append({"text": clause_text.strip(), "raw_score": raw_score, "hits": hits})

        raw_scores = [c["raw_score"] for c in clause_results]
        is_mixed = (
            had_contrast and len(raw_scores) >= 2
            and any(a > 0 and b < 0 or a < 0 and b > 0 for a, b in zip(raw_scores[:-1], raw_scores[1:])
                    if abs(a) >= _MIXED_MIN_CLAUSE_MAGNITUDE and abs(b) >= _MIXED_MIN_CLAUSE_MAGNITUDE)
        )
        total_raw = sum(raw_scores) if not is_mixed else (sum(raw_scores) / len(raw_scores))
        score = max(-1.0, min(1.0, total_raw / _NORMALIZATION_DIVISOR))

        if is_mixed:
            label = "MIXED"
        elif score > 0.1:
            label = "POSITIVE"
        elif score < -0.1:
            label = "NEGATIVE"
        else:
            label = "NEUTRAL"

        all_hits = [h for c in clause_results for h in c["hits"]]
        has_positive_hit = any(h["contribution"] > 0 for h in all_hits)
        has_negative_hit = any(h["contribution"] < 0 for h in all_hits)
        # "Ambiguous" means hits genuinely pulling in opposite directions that
        # net out near zero - not merely one weak same-direction hit (e.g. a
        # lone "maintains" is a confident NEUTRAL, not an ambiguous one).
        is_ambiguous = is_mixed or (has_positive_hit and has_negative_hit and abs(score) < config.MIXED_ESCALATION_ABS_SCORE)
        confidence = min(1.0, len(all_hits) * 0.25) if all_hits else 0.0

        return {
            "score": round(score, 3), "label": label, "confidence": round(confidence, 3),
            "is_ambiguous": is_ambiguous, "trace": clause_results,
        }


class LLMSentimentClassifier(SentimentClassifier):
    """Tier-2 escalation path - plain REST call, no provider SDK, so pointing
    LLM_SENTIMENT_API_URL/API_KEY at a different provider is the entire
    "swap the provider" story. Disabled by default (empty key/url, same
    convention as IPO_GURU_API_KEY) - falls back to the Tier-0 result on any
    failure or when not configured, so callers never need their own
    try/except around this."""

    def __init__(self, fallback: SentimentClassifier):
        self.fallback = fallback

    def classify(self, text: str) -> dict:
        if not config.LLM_SENTIMENT_ENABLED or not config.LLM_SENTIMENT_API_KEY or not config.LLM_SENTIMENT_API_URL:
            return self.fallback.classify(text)
        try:
            response = requests.post(
                config.LLM_SENTIMENT_API_URL,
                headers={"Authorization": f"Bearer {config.LLM_SENTIMENT_API_KEY}"},
                json={"text": text},
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            return {
                "score": max(-1.0, min(1.0, float(payload["score"]))),
                "label": str(payload["label"]).upper(),
                "confidence": max(0.0, min(1.0, float(payload.get("confidence", 0.7)))),
                "is_ambiguous": False,
                "trace": [{"tier": "llm", "raw_response": payload}],
            }
        except Exception as exc:
            fallback_result = self.fallback.classify(text)
            fallback_result["trace"] = [{"tier": "llm_failed_fallback_to_lexicon", "error": str(exc)}] + fallback_result["trace"]
            return fallback_result


_lexicon_classifier = LexiconSentimentClassifier()
_tiered_classifier = LLMSentimentClassifier(fallback=_lexicon_classifier)


def classify_headlines(headlines: list[str]) -> dict:
    """Aggregates a list of headline titles into the legacy score_headlines()
    shape ({score: int[-15,15], label, headlines: [{title,sentiment}], note}),
    so every existing caller in main.py keeps working unmodified. Never
    escalates to Tier-2 - this is the free path the once-daily ~2,300-symbol
    scan (indirectly, via analyze_news_sentiment) also runs through, so it
    must stay zero-cost regardless of how ambiguous a headline looks."""
    if not headlines:
        return {"score": 0, "label": "Neutral", "headlines": [], "note": "No recent news found for this symbol."}

    scored_headlines = []
    total_score = 0.0
    mixed_count = 0
    for title in headlines[:8]:
        result = classify_text(title)
        label = "Mixed" if result["label"] == "MIXED" else result["label"].capitalize()
        if label == "Mixed":
            mixed_count += 1
        total_score += result["score"]
        scored_headlines.append({"title": title, "sentiment": label})

    average_score = total_score / len(scored_headlines)
    bounded_score = round(max(-15.0, min(15.0, average_score * 15)))
    if mixed_count and abs(bounded_score) <= 5:
        label = "Mixed"
    elif bounded_score > 2:
        label = "Positive"
    elif bounded_score < -2:
        label = "Negative"
    else:
        label = "Neutral"

    return {
        "score": bounded_score,
        "label": label,
        "headlines": scored_headlines,
        "note": f"Lexicon-based financial sentiment scan of {len(scored_headlines)} recent headlines (negation- and contrast-aware, not full NLP).",
    }


def classify_text(text: str, allow_llm_escalation: bool = False, force_escalate: bool = False) -> dict:
    """Single entry point the rest of the pipeline should call. Tier-2 is
    only ever reached when the caller explicitly opts in (allow_llm_escalation)
    AND EITHER Tier-0 itself flags the text as ambiguous OR the caller has
    independently determined this is a high-impact event (force_escalate,
    set by pipeline.py from the article's event_type - see
    config.HIGH_IMPACT_EVENT_TYPES) - the daily scan and the RSS poller must
    never pass allow_llm_escalation=True, so force_escalate never actually
    reaches Tier-2 from those paths regardless of event_type."""
    lexicon_result = _lexicon_classifier.classify(text)
    if allow_llm_escalation and (lexicon_result["is_ambiguous"] or force_escalate):
        return _tiered_classifier.classify(text)
    return lexicon_result
