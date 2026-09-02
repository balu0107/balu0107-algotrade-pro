"""Is an article actually about this company - or just mentioning it in
passing, covering its whole sector, or a market-wide roundup? Not ML: a
positional/keyword heuristic (ticker/name/alias in the title vs. only in the
description, a sector-keyword fallback, a discount for roundup framing) that's
cheap enough to run on every candidate article before the comparatively more
expensive sentiment step - see pipeline.py, which drops anything below
config.RELEVANCE_DISCARD_THRESHOLD before sentiment ever runs on it.
"""
import re

from . import config
from .aliases import get_aliases, get_sector_keywords
from .lexicon import MARKET_ROUNDUP_PHRASES

_GENERIC_SUFFIXES = re.compile(
    r"\b(limited|ltd|industries|corp|corporation|company|india|inc|plc|group|holdings)\b"
)


def _bare_name_phrase(company_name: str) -> str:
    """Fallback for symbols with no hand-curated alias (aliases.py only
    covers the highest-traffic ~80): strip generic corporate suffixes and
    return whatever significant phrase remains, e.g. "Asian Paints Limited"
    -> "asian paints". Deliberately matched as one contiguous PHRASE, not as
    any-of-its-individual-words - "Oil & Natural Gas Corp" stripped to just
    "oil" would false-positive on every generic "oil prices" sector story;
    requiring the full "oil natural gas" phrase avoids that."""
    stripped = _GENERIC_SUFFIXES.sub("", company_name.lower()).replace("&", " and ")
    stripped = re.sub(r"[^a-z0-9 ]", " ", stripped)
    return re.sub(r"\s+", " ", stripped).strip()


# Real NSE tickers that double as common English/business words - a bare
# uppercase-token ticker match is unsafe for these (spotted live: "OIL" for
# Oil India false-positived on "crude oil prices", "RETAIL" false-positived
# on "expand retail access to bonds" - neither headline was about that
# company at all). Extend this list as more collisions turn up in practice.
_AMBIGUOUS_TICKER_WORDS = {
    "oil", "retail", "idea", "page", "star", "rain", "deep", "gold", "cash",
    "focus", "trend", "life", "bank", "auto", "steel", "power", "up", "down",
    "buy", "sell", "hold", "value", "growth", "max", "info", "tech",
}


def _bare_ticker_hit(symbol: str, original_title: str) -> bool:
    """A bare ticker mention is only trusted when it's written the way real
    ticker call-outs actually look - an isolated ALL-CAPS token in the
    ORIGINAL-case title, not merely present after lowercasing - and the
    ticker isn't one of the common-word collisions above."""
    if len(symbol) < 3 or symbol.lower() in _AMBIGUOUS_TICKER_WORDS:
        return False
    return re.search(r"\b" + re.escape(symbol.upper()) + r"\b", original_title) is not None


def _contains_phrase(haystack: str, phrase: str) -> bool:
    if not phrase:
        return False
    return re.search(r"\b" + re.escape(phrase.lower()) + r"\b", haystack) is not None


def _normalize(text: str) -> str:
    """Same &->and / punctuation-to-space normalization as _bare_name_phrase,
    applied to the article text so a bare-name phrase match compares like
    with like regardless of which side happens to spell out "&" vs "and"."""
    normalized = text.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9 ]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def score_relevance(symbol: str, company_name: str, title: str, description: str = "", sector: str | None = None) -> dict:
    """Returns {"score": float[0,1], "reasons": [str, ...]}. The reasons list
    is exactly the debug trail behind "why did this article count/not count" -
    which match tier fired and what discount applied, in order."""
    title_lc = (title or "").lower()
    description_lc = (description or "").lower()
    combined = f"{title_lc} {description_lc}"

    aliases = get_aliases(symbol)
    bare_phrase = _bare_name_phrase(company_name)
    title_normalized = _normalize(title_lc)
    description_normalized = _normalize(description_lc)

    canonical_hit_in_title = _contains_phrase(title_lc, company_name) or _bare_ticker_hit(symbol, title or "")
    alias_hit_in_title = any(_contains_phrase(title_lc, a) for a in aliases)
    bare_hit_in_title = len(bare_phrase) >= 4 and _contains_phrase(title_normalized, bare_phrase)

    name_in_description_only = not (canonical_hit_in_title or alias_hit_in_title or bare_hit_in_title) and (
        _contains_phrase(description_lc, company_name)
        or any(_contains_phrase(description_lc, a) for a in aliases)
        or (len(bare_phrase) >= 4 and _contains_phrase(description_normalized, bare_phrase))
    )

    reasons = []
    if canonical_hit_in_title:
        score = config.RELEVANCE_TITLE_MATCH
        reasons.append(f"canonical name/ticker matched in title (base {score})")
    elif alias_hit_in_title:
        score = config.RELEVANCE_ALIAS_TITLE_MATCH
        reasons.append(f"known alias matched in title (base {score})")
    elif bare_hit_in_title:
        score = config.RELEVANCE_ALIAS_TITLE_MATCH - 0.1  # a bare-name-phrase match is a notch less certain than a curated alias
        reasons.append(f"bare company-name phrase matched in title (base {score:.2f})")
    elif name_in_description_only:
        score = config.RELEVANCE_NAME_IN_DESCRIPTION
        reasons.append(f"name/alias matched only in the description, not the title (base {score})")
    else:
        sector_hits = [kw for kw in get_sector_keywords(sector) if _contains_phrase(combined, kw)]
        if not sector_hits:
            return {"score": 0.0, "reasons": ["no name/alias/sector-keyword match found"]}
        score = min(
            config.RELEVANCE_SECTOR_KEYWORD_CAP,
            config.RELEVANCE_SECTOR_KEYWORD_BASE + config.RELEVANCE_SECTOR_KEYWORD_STEP * (len(sector_hits) - 1),
        )
        reasons.append(f"sector-wide keyword(s) matched {sector_hits} (base {score:.2f})")

    # A mention right at the start of the title reads as clearly "about" this
    # company; buried later (e.g. a byline-adjacent aside) is less certain.
    if canonical_hit_in_title or alias_hit_in_title or bare_hit_in_title:
        lead = title_lc[: config.RELEVANCE_TITLE_POSITION_CHARS]
        candidates = [company_name.lower(), symbol.lower(), *[a.lower() for a in aliases], bare_phrase]
        if any(c and c in lead for c in candidates):
            score += config.RELEVANCE_TITLE_POSITION_BONUS
            reasons.append(f"mention lands in the first {config.RELEVANCE_TITLE_POSITION_CHARS} chars of the title (+{config.RELEVANCE_TITLE_POSITION_BONUS})")

    if any(_contains_phrase(combined, phrase) for phrase in MARKET_ROUNDUP_PHRASES):
        score *= config.ROUNDUP_DISCOUNT
        reasons.append(f"market-roundup phrasing detected (\"market rises\", \"top gainers\", ...) - discounted x{config.ROUNDUP_DISCOUNT}")

    score = max(0.0, min(1.0, score))
    return {"score": round(score, 3), "reasons": reasons}
