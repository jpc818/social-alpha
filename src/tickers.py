"""Ticker extraction helpers for meme-stock social text."""

from __future__ import annotations

import re

# Common false positives in finance chatter
_BLOCKLIST = {
    "USD", "CEO", "CFO", "CTO", "IPO", "ATH", "ATL", "ETF", "NYSE", "SEC",
    "FDA", "AI", "EV", "DD", "YOLO", "FOMO", "IMO", "TLDR", "USA", "GDP",
    "API", "EPS", "PE", "WSB", "OTC", "AM", "PM", "EST", "PST", "GMT",
    "AFAIK", "BS", "BUY", "CAD", "CNBC", "CPI", "DID", "DOT", "FUD", "IS",
    "RIP", "SPAC", "SS", "US", "USDT", "VR", "WE", "WILL", "YT", "AED",
    "NZ", "UK", "UAE", "OTM", "IDF", "KYC", "ALL", "APP", "PSA", "RH",
}

_CASHTAG = re.compile(r"\$([A-Z]{1,5})\b")
_UPPER = re.compile(r"\b([A-Z]{2,5})\b")


def extract_tickers(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    for match in _CASHTAG.findall(text.upper()):
        if match not in _BLOCKLIST and match not in found:
            found.append(match)
    # Only add bare uppercase tokens when cashtag already present or clearly stock-like
    if found:
        return found
    for match in _UPPER.findall(text):
        if match in _BLOCKLIST or match in found:
            continue
        # Prefer tokens that look like tickers in meme contexts when $ is missing
        if len(match) <= 5:
            found.append(match)
    return found[:8]
