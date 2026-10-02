"""Offline / no-Reddit ingest: seed tickers + bundled sample posts + optional NewsAPI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from src.config import load_config, project_root
from src.sentiment import analyze_dataset
from src.store import Store, utc_now


def _load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    return data if isinstance(data, list) else []


def _sample_reddit_posts() -> list[dict[str, Any]]:
    raw = _load_json(project_root() / "data" / "raw" / "reddit_posts.json")
    out = []
    for post in raw:
        pid = post.get("id") or post.get("url") or post.get("title")
        out.append(
            {
                "id": f"sample-reddit:{pid}",
                "source": "sample_reddit",
                "created_at": post.get("created_utc") or post.get("created_at"),
                "title": post.get("title", ""),
                "body": post.get("body") or post.get("selftext") or "",
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "url": post.get("url", ""),
                "subreddit": post.get("subreddit", "sample"),
            }
        )
    return out


def _seed_mentions(seed_tickers: list[str]) -> list[dict[str, Any]]:
    """Synthetic buzz rows so strategy has signals without live social APIs."""
    templates = [
        ("Positive buzz on ${t}", "Seeing unusual volume and squeeze chatter on ${t}. Bullish setup."),
        ("${t} momentum", "Retail flow picking up in ${t}. Watching breakout."),
        ("Caution on ${t}", "Some profit taking talk around ${t} but still active."),
    ]
    mentions = []
    for i, ticker in enumerate(seed_tickers):
        title_t, body_t = templates[i % len(templates)]
        mentions.append(
            {
                "id": f"seed:{ticker}:{i}",
                "source": "seed",
                "created_at": utc_now(),
                "title": title_t.replace("${t}", ticker),
                "body": body_t.replace("${t}", f"${ticker}"),
                "score": 50 + i * 7,
                "num_comments": 10 + i * 3,
                "url": "",
                "subreddit": "seed",
                "tickers": [ticker],
            }
        )
    return mentions


def _fetch_news(keywords: list[str], limit: int) -> list[dict[str, Any]]:
    cfg = load_config()
    api_key = cfg["_env"].get("NEWS_API_KEY") or ""
    if not api_key:
        print("[INFO] NEWS_API_KEY not set — skipping live news ingest")
        return []

    query = " OR ".join(keywords)
    resp = requests.get(
        "https://newsapi.org/v2/everything",
        params={
            "q": query,
            "apiKey": api_key,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": limit,
        },
        timeout=30,
    )
    resp.raise_for_status()
    articles = resp.json().get("articles", [])
    out = []
    for i, article in enumerate(articles):
        out.append(
            {
                "id": f"news:{article.get('url', i)}",
                "source": "news",
                "created_at": article.get("publishedAt"),
                "title": article.get("title") or "",
                "body": " ".join(
                    filter(None, [article.get("description") or "", article.get("content") or ""])
                ),
                "score": 0,
                "num_comments": 0,
                "url": article.get("url") or "",
                "subreddit": article.get("source", {}).get("name", "news"),
            }
        )
    print(f"[INFO] Fetched {len(out)} news articles")
    return out


def _sample_news() -> list[dict[str, Any]]:
    raw = _load_json(project_root() / "data" / "raw" / "news.json")
    out = []
    for i, article in enumerate(raw):
        out.append(
            {
                "id": f"sample-news:{article.get('url', i)}",
                "source": "sample_news",
                "created_at": article.get("published_at") or article.get("publishedAt"),
                "title": article.get("title", ""),
                "body": " ".join(
                    filter(
                        None,
                        [
                            article.get("description") or "",
                            article.get("content") or "",
                        ],
                    )
                ),
                "score": 0,
                "num_comments": 0,
                "url": article.get("url", ""),
                "subreddit": article.get("source", "news"),
            }
        )
    return out


def ingest_offline(store: Store) -> list[dict[str, Any]]:
    cfg = load_config()
    seed = [t.upper() for t in (cfg.get("universe", {}).get("seed_tickers") or [])]
    news_cfg = cfg.get("news", {})

    posts: list[dict[str, Any]] = []
    posts.extend(_sample_reddit_posts())
    posts.extend(_seed_mentions(seed))
    posts.extend(_sample_news())
    if news_cfg.get("enabled"):
        posts.extend(_fetch_news(news_cfg.get("keywords") or seed, int(news_cfg.get("limit", 30))))

    analyzed = analyze_dataset(
        posts,
        text_fields=("title", "body"),
        provider=cfg["sentiment"]["provider"],
        openai_model=cfg["sentiment"].get("openai_model", "gpt-4o-mini"),
    )

    # Ensure seed tickers stick even if VADER misses cashtags in title-only rows
    seed_set = set(seed)
    for item in analyzed:
        tickers = [t.upper() for t in (item.get("tickers") or [])]
        for t in seed_set:
            title = item.get("title") or ""
            body = item.get("body") or ""
            if t in title.upper() or f"${t}" in (title + " " + body).upper():
                if t not in tickers:
                    tickers.append(t)
        item["tickers"] = tickers
        item["ingested_at"] = utc_now()
        item["raw"] = {k: item.get(k) for k in ("title", "body", "url", "source")}
        store.upsert_mention(item)

    print(f"[INFO] Offline ingest complete: {len(analyzed)} mentions (seeds={seed})")
    return analyzed
