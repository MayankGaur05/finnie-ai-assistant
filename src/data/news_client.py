"""Marketaux client for recent financial-news article metadata."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import truststore
import yaml
from dotenv import load_dotenv
from pathlib import Path

truststore.inject_into_ssl()
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
with (PROJECT_ROOT / "config.yaml").open(encoding="utf-8") as config_file:
    NEWS_CONFIG = yaml.safe_load(config_file).get("news_data", {})

API_URL = str(NEWS_CONFIG.get("api_url", "https://api.marketaux.com/v1/news/all"))
TIMEOUT_SECONDS = int(NEWS_CONFIG.get("request_timeout_seconds", 15))
LOOKBACK_DAYS = int(NEWS_CONFIG.get("lookback_days", 7))
MAX_ARTICLES = min(3, max(1, int(NEWS_CONFIG.get("max_articles", 3))))


class NewsDataError(RuntimeError):
    """Raised when Marketaux cannot return usable news data."""


def search_financial_news(query: str) -> list[dict[str, str]]:
    """Return recent article metadata for a financial-news query.

    The Marketaux free tier returns up to three articles per request. Only
    title/description/snippet metadata is used; article pages are not scraped.
    """
    api_token = os.getenv("MARKETAUX_API_TOKEN") or os.getenv("MARKETAUX_API_KEY")
    if not api_token:
        raise NewsDataError("MARKETAUX_API_TOKEN is missing from the environment.")

    search_query = _clean_query(query)
    if not search_query:
        return []

    now = datetime.now(timezone.utc)
    published_after = now - timedelta(days=LOOKBACK_DAYS)
    params = {
        "api_token": api_token,
        "search": search_query,
        "language": "en",
        "published_after": published_after.strftime("%Y-%m-%dT%H:%M:%S"),
        "published_before": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "sort": "published_on",
        "group_similar": "true",
        "limit": str(MAX_ARTICLES),
    }
    request = Request(
        f"{API_URL}?{urlencode(params)}",
        headers={"User-Agent": "FinniePersonalFinanceAssistant/0.1"},
    )

    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Do not include the request URL in errors: Marketaux puts the token
        # in the query string.
        raise NewsDataError(
            f"Marketaux rejected the news request (HTTP {exc.code}). "
            "Check the API token and plan allowance."
        ) from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise NewsDataError("Could not retrieve news from Marketaux.") from exc

    if not isinstance(payload, dict):
        raise NewsDataError("Marketaux returned an invalid response.")
    if payload.get("error"):
        error_message = payload["error"]
        if isinstance(error_message, dict):
            error_message = error_message.get("message", "provider error")
        raise NewsDataError(f"Marketaux returned an API error: {error_message}")

    raw_articles = payload.get("data", [])
    if not isinstance(raw_articles, list):
        raise NewsDataError("Marketaux returned an invalid article list.")

    articles: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for article in raw_articles[:MAX_ARTICLES]:
        if not isinstance(article, dict):
            continue
        title = _clean_text(article.get("title"))
        url = _clean_text(article.get("url"))
        if not title or not url.startswith("https://") or url in seen_urls:
            continue
        seen_urls.add(url)
        articles.append(
            {
                "title": title[:500],
                "description": _clean_text(article.get("description"))[:1500],
                "snippet": _clean_text(article.get("snippet"))[:1500],
                "publisher": _clean_text(article.get("source"))[:200],
                "published_at": _clean_text(article.get("published_at"))[:80],
                "url": url,
            }
        )
    return articles


def _clean_query(query: str) -> str:
    """Remove common request phrasing before sending keywords to search."""
    cleaned = re.sub(r"\s+", " ", query).strip()
    cleaned = re.sub(
        r"^(?:please\s+)?(?:summari[sz]e|tell me|show me|find|search for|what(?:'s| is)?|"
        r"give me)\s+(?:the\s+)?(?:latest\s+|recent\s+|current\s+)?"
        r"(?:financial\s+)?(?:news|headlines|updates)?\s*(?:about|on|for)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:this week|past week|last 7 days|past 7 days|last week|recent news)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ?.,:;-")
    return cleaned[:200]


def _clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()
