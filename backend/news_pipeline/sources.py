"""NewsSource abstraction (spec section 1): fetch_news(symbol, company_name,
time_window_hours) -> list of normalized article dicts. Sources can be added
independently - each is just a small class implementing this one method.

RSS sources here are market-WIDE feeds (not per-symbol), so their fetch_news
ignores symbol/company_name entirely and returns everything from the feed
within the time window - relevance.py (run later, in the pipeline) is what
actually decides which symbols an article applies to, not the source itself.

Verified live and fresh by hand on 2026-08-23: Economic Times Markets,
Business Standard Markets, BusinessLine Stock Markets (all three showed a
same-day lastBuildDate and current items). Deliberately NOT included:
Moneycontrol's rss/*.xml feeds (every variant checked - marketreports,
business, latestnews, buzzingstocks, results, economy - was frozen since
mid-2024, i.e. discontinued) and Reuters (no free public RSS anymore; their
real feed is the paid Reuters Connect product; DNS for the old feed URL
doesn't even resolve). Both are natural extension points if a working/paid
feed shows up later - just add another RssSource(...) to ACTIVE_RSS_SOURCES.
"""
import datetime
import re
from abc import ABC, abstractmethod
from xml.etree import ElementTree

import requests

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


class NewsSource(ABC):
    @abstractmethod
    def fetch_news(self, symbol, company_name, time_window_hours: float) -> list:
        """Returns normalized dicts: {source, title, url, published_at, description}."""
        ...


_RSS_DATE_FORMATS = ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z")


def _parse_rss_date(raw: str) -> datetime.datetime:
    if not raw:
        return datetime.datetime.utcnow()
    for fmt in _RSS_DATE_FORMATS:
        try:
            return datetime.datetime.strptime(raw.strip(), fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return datetime.datetime.utcnow()


def _strip_html(text: str) -> str:
    """RSS <description> fields routinely carry an inline <img>/entities
    (seen hand-inspecting real feed output) - strip markup so relevance/
    sentiment see plain text, not tag soup. A regex strip is enough for this
    (no new HTML-parser dependency needed just for feed descriptions)."""
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", _HTML_TAG_RE.sub(" ", text)).strip()


class RssSource(NewsSource):
    """Generic RSS 2.0 adapter using stdlib xml.etree - no new dependency.
    Tolerant of the minor per-outlet quirks (CDATA, occasional missing
    pubDate) seen when hand-testing the three feeds below; ElementTree
    already unwraps CDATA transparently."""

    def __init__(self, name: str, feed_url: str, timeout: int = 15):
        self.name = name
        self.feed_url = feed_url
        self.timeout = timeout

    def fetch_news(self, symbol=None, company_name=None, time_window_hours=48) -> list:
        response = requests.get(self.feed_url, timeout=self.timeout, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=time_window_hours)

        articles = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            published_at = _parse_rss_date(item.findtext("pubDate"))
            if published_at < cutoff:
                continue
            link = (item.findtext("link") or "").strip()
            articles.append({
                "source": self.name, "title": title,
                "url": link or f"rss://{self.name}/{abs(hash(title))}",
                "published_at": published_at,
                "description": _strip_html(item.findtext("description") or ""),
            })
        return articles


# See module docstring for why exactly these three and no others.
ECONOMIC_TIMES = RssSource("economic_times", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms")
BUSINESS_STANDARD = RssSource("business_standard", "https://www.business-standard.com/rss/markets-106.rss")
BUSINESSLINE = RssSource("businessline", "https://www.thehindubusinessline.com/markets/stock-markets/feeder/default.rss")

ACTIVE_RSS_SOURCES = [ECONOMIC_TIMES, BUSINESS_STANDARD, BUSINESSLINE]
