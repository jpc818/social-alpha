"""Load YAML config and environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def project_root() -> Path:
    return ROOT


@lru_cache(maxsize=1)
def load_config(path: str | None = None) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with cfg_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data["_env"] = {
        "LIVE_TRADING": os.getenv("LIVE_TRADING", "false").lower() in {"1", "true", "yes"},
        "REDDIT_CLIENT_ID": os.getenv("REDDIT_CLIENT_ID", ""),
        "REDDIT_CLIENT_SECRET": os.getenv("REDDIT_CLIENT_SECRET", ""),
        "REDDIT_USER_AGENT": os.getenv("REDDIT_USER_AGENT", "social-alpha/0.1"),
        "NEWS_API_KEY": os.getenv("NEWS_API_KEY", ""),
        "TWITTER_BEARER_TOKEN": os.getenv("TWITTER_BEARER_TOKEN", ""),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "SCHWAB_APP_KEY": os.getenv("SCHWAB_APP_KEY", ""),
        "SCHWAB_APP_SECRET": os.getenv("SCHWAB_APP_SECRET", ""),
        "SCHWAB_CALLBACK_URL": os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182"),
        "SCHWAB_TOKEN_PATH": os.getenv("SCHWAB_TOKEN_PATH", str(ROOT / "schwab_token.json")),
    }
    return data
