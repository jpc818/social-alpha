"""Naive meme-sentiment strategy for paper trading."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.paper import PaperBroker
from src.store import Store


def aggregate_ticker_signals(mentions: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = defaultdict(
        lambda: {"mentions": 0.0, "score_sum": 0.0, "sentiment_sum": 0.0, "comments": 0.0}
    )
    for m in mentions:
        for ticker in m.get("tickers") or []:
            t = ticker.upper()
            stats[t]["mentions"] += 1
            stats[t]["score_sum"] += float(m.get("score") or 0)
            stats[t]["sentiment_sum"] += float(m.get("sentiment_score") or 0)
            stats[t]["comments"] += float(m.get("num_comments") or 0)
    out = {}
    for ticker, s in stats.items():
        n = max(s["mentions"], 1.0)
        out[ticker] = {
            "mentions": s["mentions"],
            "avg_score": s["score_sum"] / n,
            "avg_sentiment": s["sentiment_sum"] / n,
            "avg_comments": s["comments"] / n,
        }
    return out


def run_strategy(store: Store, broker: PaperBroker, prices: dict[str, float]) -> list[dict[str, Any]]:
    from src.config import load_config

    cfg = load_config()
    seed = {t.upper() for t in (cfg.get("universe", {}).get("seed_tickers") or [])}
    mode = (cfg.get("ingest") or {}).get("mode", "offline")

    mentions = store.recent_mentions(300)
    signals = aggregate_ticker_signals(mentions)
    if mode == "offline" and seed:
        signals = {t: s for t, s in signals.items() if t in seed}
        prices = {t: p for t, p in prices.items() if t in seed}

    actions: list[dict[str, Any]] = []

    # Rank by mention velocity * sentiment
    ranked = sorted(
        signals.items(),
        key=lambda kv: kv[1]["mentions"] * (1 + kv[1]["avg_sentiment"]),
        reverse=True,
    )

    positions = store.get_positions()

    # Exit weak sentiment holdings
    for ticker in list(positions):
        if seed and ticker not in seed:
            # Flatten non-seed leftovers from earlier demos
            if ticker in broker.store.latest_prices() or ticker in prices:
                px = prices.get(ticker) or broker.store.latest_prices().get(ticker)
                if px is not None:
                    actions.append(broker.sell(ticker, float(px), reason="non_seed_exit"))
            continue
        sig = signals.get(ticker)
        if sig and sig["avg_sentiment"] < -0.05:
            if ticker in prices:
                actions.append(broker.sell(ticker, prices[ticker], reason="sentiment_fade"))

    # Enter top buzz names still positively skewed
    for ticker, sig in ranked[:5]:
        if ticker not in prices:
            continue
        if sig["mentions"] < 2 or sig["avg_sentiment"] < 0.05:
            continue
        if ticker in store.get_positions():
            continue
        actions.append(
            broker.buy(
                ticker,
                prices[ticker],
                reason=f"buzz mentions={sig['mentions']:.0f} sent={sig['avg_sentiment']:.2f}",
            )
        )
        break  # one new entry per cycle for $1k risk control

    broker.mark_to_market(prices if prices else store.latest_prices())
    return actions
