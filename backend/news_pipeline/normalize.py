"""Raw source payloads -> the one normalized shape every later pipeline stage
expects: {source, title, url, published_at (datetime), description}.

Yahoo's news dicts show up in more than one shape (sometimes a top-level
"title"/"link"/"providerPublishTime", sometimes nested under "content" with
"title"/"canonicalUrl"/"pubDate") - handled the same tolerant way main.py's
own extract_headline_title already does for titles, extended here to also
recover a URL and a publish timestamp.
"""
import datetime


def _get_content(article: dict) -> dict:
    content = article.get("content")
    return content if isinstance(content, dict) else {}


def _extract_url(article: dict, content: dict, fallback: str):
    canonical = content.get("canonicalUrl")
    if isinstance(canonical, dict) and canonical.get("url"):
        return canonical["url"]
    return article.get("link") or content.get("link") or fallback


def _extract_published_at(article: dict, content: dict) -> datetime.datetime:
    raw = content.get("pubDate") or article.get("providerPublishTime")
    if isinstance(raw, (int, float)):
        try:
            return datetime.datetime.utcfromtimestamp(raw)
        except (ValueError, OSError):
            pass
    if isinstance(raw, str):
        try:
            return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.datetime.utcnow()


def normalize_yfinance_article(article, source: str, fallback_index: int = 0):
    if not isinstance(article, dict):
        return None
    content = _get_content(article)
    title = content.get("title") or article.get("title")
    if not title:
        return None
    fallback_url = f"yfinance://{source}/{fallback_index}/{abs(hash(title))}"
    return {
        "source": source,
        "title": str(title),
        "url": str(_extract_url(article, content, fallback_url)),
        "published_at": _extract_published_at(article, content),
        "description": str(content.get("summary") or article.get("summary") or ""),
    }


def normalize_yfinance_articles(articles: list, source: str) -> list:
    normalized = []
    for i, article in enumerate(articles or []):
        item = normalize_yfinance_article(article, source, fallback_index=i)
        if item:
            normalized.append(item)
    return normalized
