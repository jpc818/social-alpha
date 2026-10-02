"""Sentiment scoring: VADER (default) or optional OpenAI."""

from __future__ import annotations

import json
import os
from typing import Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from src.tickers import extract_tickers

_analyzer = SentimentIntensityAnalyzer()


def _label_from_compound(compound: float) -> str:
    if compound >= 0.05:
        return "Positive"
    if compound <= -0.05:
        return "Negative"
    return "Neutral"


def analyze_text_vader(text: str) -> dict[str, Any]:
    scores = _analyzer.polarity_scores(text or "")
    return {
        "sentiment": _label_from_compound(scores["compound"]),
        "sentiment_score": float(scores["compound"]),
        "tickers": extract_tickers(text or ""),
    }


def analyze_text_openai(text: str, model: str = "gpt-4o-mini") -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = f"""
You are a financial sentiment and ticker analyzer.
1. Classify sentiment as Positive, Negative, or Neutral.
2. Extract stock tickers (e.g. AAPL, GME). Empty list if none.
Return ONLY valid JSON: {{"sentiment":"...","tickers":["..."],"sentiment_score":0.0}}
Text: {text!r}
"""
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    content = response.choices[0].message.content or "{}"
    try:
        result = json.loads(content.strip())
    except json.JSONDecodeError:
        result = {"sentiment": "Neutral", "tickers": [], "sentiment_score": 0.0}
    result.setdefault("tickers", extract_tickers(text or ""))
    if "sentiment_score" not in result:
        mapping = {"Positive": 0.5, "Negative": -0.5, "Neutral": 0.0}
        result["sentiment_score"] = mapping.get(result.get("sentiment", "Neutral"), 0.0)
    return result


def analyze_text(text: str, provider: str = "vader", openai_model: str = "gpt-4o-mini") -> dict[str, Any]:
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        return analyze_text_openai(text, model=openai_model)
    return analyze_text_vader(text)


def analyze_dataset(
    dataset: list[dict[str, Any]],
    text_fields: tuple[str, ...] = ("title", "body", "description", "content"),
    provider: str = "vader",
    openai_model: str = "gpt-4o-mini",
) -> list[dict[str, Any]]:
    results = []
    for item in dataset:
        combined = " ".join(str(item.get(field, "") or "") for field in text_fields)
        analysis = analyze_text(combined, provider=provider, openai_model=openai_model)
        enriched = dict(item)
        enriched["sentiment"] = analysis["sentiment"]
        enriched["sentiment_score"] = analysis["sentiment_score"]
        # Prefer cashtag extraction; fall back to model tickers
        tickers = extract_tickers(combined) or analysis.get("tickers", [])
        enriched["tickers"] = [t.upper() for t in tickers]
        results.append(enriched)
    return results
