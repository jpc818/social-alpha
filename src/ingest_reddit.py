"""Reddit ingest for meme subreddits → SQLite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import praw

from src.config import load_config
from src.sentiment import analyze_dataset
from src.store import Store, utc_now


def _reddit_client() -> praw.Reddit:
    cfg = load_config()
    env = cfg["_env"]
    if not env["REDDIT_CLIENT_ID"] or not env["REDDIT_CLIENT_SECRET"]:
        raise ValueError("Missing REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET in .env")
    return praw.Reddit(
        client_id=env["REDDIT_CLIENT_ID"],
        client_secret=env["REDDIT_CLIENT_SECRET"],
        user_agent=env["REDDIT_USER_AGENT"],
    )


def fetch_reddit_posts(
    keywords: list[str] | None = None,
    subreddits: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    cfg = load_config()["reddit"]
    keywords = keywords or cfg["keywords"]
    subreddits = subreddits or cfg["subreddits"]
    limit = limit or int(cfg["post_limit"])

    reddit = _reddit_client()
    results: list[dict[str, Any]] = []
    subreddit = reddit.subreddit("+".join(subreddits))
    query = " OR ".join(keywords)
    print(f"[INFO] Reddit search: {query!r} in {','.join(subreddits)} (limit={limit})")

    for post in subreddit.search(query, sort="new", limit=limit):
        results.append(
            {
                "id": f"reddit:{post.id}",
                "source": "reddit",
                "created_at": datetime.fromtimestamp(post.created_utc, tz=timezone.utc).isoformat(),
                "title": post.title,
                "body": post.selftext,
                "score": post.score,
                "num_comments": post.num_comments,
                "url": post.url,
                "subreddit": post.subreddit.display_name,
            }
        )

    # Also pull hot posts (meme names often appear without keyword match)
    for name in subreddits:
        for post in reddit.subreddit(name).hot(limit=max(10, limit // len(subreddits))):
            item = {
                "id": f"reddit:{post.id}",
                "source": "reddit",
                "created_at": datetime.fromtimestamp(post.created_utc, tz=timezone.utc).isoformat(),
                "title": post.title,
                "body": post.selftext,
                "score": post.score,
                "num_comments": post.num_comments,
                "url": post.url,
                "subreddit": post.subreddit.display_name,
            }
            if item["id"] not in {r["id"] for r in results}:
                results.append(item)

    return results


def ingest_reddit(store: Store) -> list[dict[str, Any]]:
    cfg = load_config()
    posts = fetch_reddit_posts()
    analyzed = analyze_dataset(
        posts,
        text_fields=("title", "body"),
        provider=cfg["sentiment"]["provider"],
        openai_model=cfg["sentiment"].get("openai_model", "gpt-4o-mini"),
    )
    for item in analyzed:
        item["ingested_at"] = utc_now()
        item["raw"] = {k: item.get(k) for k in ("title", "body", "url", "subreddit")}
        store.upsert_mention(item)
    print(f"[INFO] Ingested {len(analyzed)} Reddit mentions into SQLite")
    return analyzed
