"""Market-data node for latest single-equity quotes via Alpha Vantage."""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import truststore
import yaml

from src.core.state import CoreState
from dotenv import load_dotenv

# Use the OS trust store for HTTPS on managed office devices.
truststore.inject_into_ssl()
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
with (PROJECT_ROOT / "config.yaml").open(encoding="utf-8") as config_file:
    APP_CONFIG = yaml.safe_load(config_file)

MARKET_CONFIG = APP_CONFIG.get("market_data", {})
APPLICATION_CONFIG = APP_CONFIG.get("application", {})
API_URL = "https://www.alphavantage.co/query"
REQUEST_TIMEOUT_SECONDS = int(MARKET_CONFIG.get("request_timeout_seconds", 10))
CACHE_TTL_SECONDS = int(MARKET_CONFIG.get("cache_ttl_minutes", 15)) * 60
DEFAULT_MARKET = str(APPLICATION_CONFIG.get("default_market", "NSE"))

_TICKER_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9.-]{0,14}(?![A-Za-z0-9])")
_NON_TICKER_WORDS = {
    "ALPHA", "AV", "BSE", "BUY", "CLOSE", "CURRENT", "EXCHANGE", "FOR",
    "HIGH", "INDEX", "LOW", "MARKET", "NSE", "OF", "OPEN", "PRICE",
    "QUOTE", "SHARE", "STOCK", "THE", "TODAY", "TRADE", "VOLUME",
}
_QUOTE_CACHE: dict[str, tuple[float, dict[str, object], str]] = {}


class MarketDataError(RuntimeError):
    """Raised when Alpha Vantage data cannot be retrieved or validated."""


def market(state: CoreState) -> dict[str, object]:
    """Return the latest available quote for one explicit stock ticker."""
    user_input = state["user_input"]

    if _asks_for_historical_data(user_input):
        return _message(
            "Historical price series are not implemented in Finnie's MVP yet. "
            "I can currently look up the latest available quote for one stock ticker."
        )

    if _asks_for_index(user_input):
        return _message(
            "Index quotes are not implemented in Finnie's MVP yet. "
            "I can currently look up the latest available quote for one stock ticker."
        )

    symbols = _extract_symbols(user_input, state.get("entities", {}))
    if not symbols:
        return _message(
            "Which stock ticker should I look up? Please provide one symbol, "
            "such as IRFC or TCS.",
            needs_clarification=True,
        )
    if len(symbols) > 1:
        return _message(
            "I can look up one stock at a time. Which ticker should I check?",
            needs_clarification=True,
        )

    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise MarketDataError("ALPHA_VANTAGE_API_KEY is missing.")

    requested_symbol = symbols[0]
    try:
        instrument = _resolve_symbol(requested_symbol, api_key)
        quote, retrieved_at = _get_quote(instrument["symbol"], api_key)
    except MarketDataError:
        raise
    except Exception as exc:
        raise MarketDataError("Alpha Vantage market-data lookup failed.") from exc

    price = quote.get("05. price")
    latest_day = quote.get("07. latest trading day")
    if not price or not latest_day:
        raise MarketDataError("Alpha Vantage returned an incomplete quote.")

    currency = str(instrument.get("currency") or "")
    price_label = _format_price(price, currency)
    display_symbol = str(instrument["symbol"])
    company_name = str(instrument.get("name") or display_symbol)
    change = quote.get("09. change")
    change_percent = quote.get("10. change percent")

    response = (
        f"Alpha Vantage's latest available quote for {company_name} "
        f"({display_symbol}) is {price_label}, dated {latest_day}."
    )
    if change and change_percent:
        response += f" Change: {change} ({change_percent})."
    response += (
        " Quote freshness depends on the provider's data entitlement and market; "
        "this may be end-of-day or delayed data, not a live quote. This is market "
        "information, not a buy or sell recommendation."
    )

    tool_result = {
        "provider": "Alpha Vantage",
        "symbol": display_symbol,
        "name": company_name,
        "price": str(price),
        "currency": currency or None,
        "latest_trading_day": str(latest_day),
        "change": str(change) if change else None,
        "change_percent": str(change_percent) if change_percent else None,
        "retrieved_at_utc": retrieved_at,
        "source_url": "https://www.alphavantage.co/documentation/",
    }
    return {
        "response": response,
        "tool_result": tool_result,
        "needs_clarification": False,
        "error": "",
    }


def _extract_symbols(user_input: str, entities: dict[str, object]) -> list[str]:
    entity_symbol = entities.get("symbol") or entities.get("ticker")
    if isinstance(entity_symbol, str) and entity_symbol.strip():
        return [entity_symbol.strip().upper()]

    candidates = {
        match.group(0).upper()
        for match in _TICKER_PATTERN.finditer(user_input)
        if match.group(0).upper() not in _NON_TICKER_WORDS
        and not match.group(0).isdigit()
    }
    return sorted(candidates)


def _asks_for_historical_data(user_input: str) -> bool:
    return bool(
        re.search(
            r"\b(history|historical|performance|past\s+(week|month|year)|"
            r"last\s+(week|month|year)|52[ -]?week)\b",
            user_input,
            re.I,
        )
    )


def _asks_for_index(user_input: str) -> bool:
    return bool(
        re.search(r"\b(NIFTY|SENSEX|S&P\s*500|DOW JONES|NASDAQ|index)\b", user_input, re.I)
    )


def _api_get(params: dict[str, str], api_key: str) -> dict[str, object]:
    query = urlencode({**params, "apikey": api_key})
    request = Request(
        f"{API_URL}?{query}",
        headers={"User-Agent": "FinniePersonalFinanceAssistant/0.1"},
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise MarketDataError("Could not connect to Alpha Vantage.") from exc

    if not isinstance(payload, dict):
        raise MarketDataError("Alpha Vantage returned an invalid response.")
    if any(key in payload for key in ("Error Message", "Note", "Information")):
        raise MarketDataError(
            "Alpha Vantage could not provide this data. Check the symbol, API "
            "allowance, and provider response."
        )
    return payload


def _resolve_symbol(requested_symbol: str, api_key: str) -> dict[str, str]:
    payload = _api_get(
        {"function": "SYMBOL_SEARCH", "keywords": requested_symbol},
        api_key,
    )
    matches = payload.get("bestMatches", [])
    if not isinstance(matches, list):
        matches = []

    requested_upper = requested_symbol.upper()
    exact_matches = []
    for match in matches:
        if not isinstance(match, dict):
            continue
        candidate_symbol = str(match.get("1. symbol", "")).upper()
        base_symbol = candidate_symbol.split(".", maxsplit=1)[0]
        if candidate_symbol == requested_upper or base_symbol == requested_upper:
            exact_matches.append(match)

    if not exact_matches:
        raise MarketDataError(f"No exact market symbol was found for {requested_symbol}.")

    def match_rank(match: dict[str, object]) -> tuple[int, int, float]:
        region = str(match.get("4. region", "")).casefold()
        symbol = str(match.get("1. symbol", "")).upper()
        exchange = symbol.rsplit(".", maxsplit=1)[-1].casefold()
        preferred_exchange = int(exchange == DEFAULT_MARKET.casefold())
        preferred_region = int("india" in region)
        try:
            score = float(match.get("9. matchScore", 0))
        except (TypeError, ValueError):
            score = 0.0
        return preferred_exchange, preferred_region, score

    selected = max(exact_matches, key=match_rank)
    return {
        "symbol": str(selected.get("1. symbol", requested_symbol)),
        "name": str(selected.get("2. name", "")),
        "currency": str(selected.get("8. currency", "")),
    }


def _get_quote(symbol: str, api_key: str) -> tuple[dict[str, object], str]:
    now = time.monotonic()
    cached = _QUOTE_CACHE.get(symbol)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1], cached[2]

    payload = _api_get(
        
        {"function": "GLOBAL_QUOTE", "symbol": symbol},
        api_key,
    )
    quote = payload.get("Global Quote")
    print({key: value for key, value in payload.items() if key != "apikey"})
    if not isinstance(quote, dict) or not quote:
        raise MarketDataError(f"Alpha Vantage returned no quote for {symbol}.")

    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _QUOTE_CACHE[symbol] = (now, quote, retrieved_at)
    return quote, retrieved_at


def _format_price(price: object, currency: str) -> str:
    return f"{currency} {price}".strip()


def _message(
    response: str,
    *,
    needs_clarification: bool = False,
) -> dict[str, object]:
    return {
        "response": response,
        "needs_clarification": needs_clarification,
        "tool_result": {},
        "error": "",
    }
