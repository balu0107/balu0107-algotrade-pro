"""Collapses multiple outlets' coverage of the same real-world event into one
News Event, using stdlib string similarity + publication-time proximity - no
embeddings/vector search, per the "no vector databases" constraint. Title
similarity via difflib.SequenceMatcher (already in the standard library) is
kept as the cheap FIRST-STAGE check; two further gates below must ALSO pass
before a match is accepted, since lexical similarity alone can't tell an
EARNINGS story from a REGULATORY one, or a "Rs 8,000 crore" deal from an
unrelated "Rs 800 crore" one that just happens to read similarly.

Explicitly NOT implemented: full named-entity extraction. Symbol/company
scoping already happens one layer up in pipeline.ingest_articles (candidates
are pre-filtered to the same entity before find_matching_event ever runs), and
the event-type + number gates below cover the realistic remaining false-merge
modes without an NLP dependency - a stated limitation, not a silent gap.
"""
import difflib
import re

from . import config

TITLE_SIMILARITY_THRESHOLD = 0.55  # difflib ratio; loosely tuned against real duplicate-headline pairs (see tests)
DEDUP_TIME_WINDOW_HOURS = 72  # outlets covering "the same story" rarely spread further apart than this

_NON_ALNUM = re.compile(r"[^a-z0-9 ]")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", _NON_ALNUM.sub(" ", title.lower())).strip()


def titles_are_likely_duplicates(title_a: str, title_b: str) -> bool:
    ratio = difflib.SequenceMatcher(None, normalize_title(title_a), normalize_title(title_b)).ratio()
    return ratio >= TITLE_SIMILARITY_THRESHOLD


def _extract_numbers(text: str) -> set:
    """Numeric values (amounts, percentages, counts) mentioned in a title -
    two headlines about the same event should cite the same figures; citing
    clearly DIFFERENT numbers is evidence they're not the same event, even
    when the surrounding wording reads similarly."""
    return {n.replace(",", "") for n in _NUMBER_RE.findall(text)}


def numbers_are_compatible(title_a: str, title_b: str) -> bool:
    numbers_a, numbers_b = _extract_numbers(title_a), _extract_numbers(title_b)
    if not numbers_a or not numbers_b:
        return True  # neither/one side makes no numeric claim - nothing to contradict
    return bool(numbers_a & numbers_b)


def find_matching_event(candidate_title: str, candidate_published_at, candidate_event_type, existing_events: list[dict]):
    """existing_events: dicts with at least {"event_summary": str,
    "event_type": str, "last_seen_at": datetime}. Returns the first event
    within the time window that ALSO passes the event-type and numeric-
    compatibility gates on top of the title-similarity check, else None
    (meaning: the caller should start a new event for this article)."""
    for event in existing_events:
        age_gap_hours = abs((candidate_published_at - event["last_seen_at"]).total_seconds()) / 3600
        if age_gap_hours > DEDUP_TIME_WINDOW_HOURS:
            continue
        if not titles_are_likely_duplicates(candidate_title, event["event_summary"]):
            continue
        if config.DEDUP_REQUIRE_SAME_EVENT_TYPE and event.get("event_type") and candidate_event_type:
            if event["event_type"] != candidate_event_type:
                continue
        if config.DEDUP_REQUIRE_NUMBER_COMPATIBILITY:
            if not numbers_are_compatible(candidate_title, event["event_summary"]):
                continue
        return event
    return None
