#!/usr/bin/env python3
"""social-alpha CLI — research + paper trading (no live Schwab orders)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config, project_root
from src.ingest_offline import ingest_offline
from src.ingest_reddit import ingest_reddit
from src.market import update_prices_for_tickers
from src.paper import PaperBroker
from src.store import Store
from src.strategy import aggregate_ticker_signals, run_strategy


def db_path() -> Path:
    return project_root() / "data" / "social_alpha.db"


def cmd_ingest(_: argparse.Namespace) -> None:
    store = Store(db_path())
    mode = (load_config().get("ingest") or {}).get("mode", "offline")
    if mode == "reddit":
        ingest_reddit(store)
    else:
        ingest_offline(store)


def cmd_prices(_: argparse.Namespace) -> None:
    store = Store(db_path())
    cfg = load_config()
    seed = [t.upper() for t in (cfg.get("universe", {}).get("seed_tickers") or [])]
    mode = (cfg.get("ingest") or {}).get("mode", "offline")

    tickers: list[str] = list(seed)
    # In offline mode, prefer the curated seed list (sample JSON has many false-positive "tickers")
    if mode != "offline":
        for m in store.recent_mentions(500):
            tickers.extend(m.get("tickers") or [])

    tickers = sorted({t.upper() for t in tickers if t})
    if not tickers:
        print("[WARN] No tickers found. Set universe.seed_tickers or run ingest.")
        return
    update_prices_for_tickers(store, tickers)


def cmd_paper_once(_: argparse.Namespace) -> None:
    cfg = load_config()
    if cfg["_env"]["LIVE_TRADING"]:
        raise SystemExit("LIVE_TRADING=true is blocked in this CLI. Paper only.")
    store = Store(db_path())
    broker = PaperBroker(store)
    prices = store.latest_prices()
    if not prices:
        print("[WARN] No prices in DB. Run: python main.py prices")
        return
    actions = run_strategy(store, broker, prices)
    print(json.dumps({"actions": actions, "account": broker.summary()}, indent=2, default=str))


def cmd_status(_: argparse.Namespace) -> None:
    store = Store(db_path())
    broker = PaperBroker(store)
    mentions = store.recent_mentions(100)
    signals = aggregate_ticker_signals(mentions)
    print(
        json.dumps(
            {
                "account": broker.summary(),
                "top_signals": dict(list(sorted(signals.items(), key=lambda kv: kv[1]["mentions"], reverse=True))[:10]),
                "mention_count": len(mentions),
                "prices": store.latest_prices(),
            },
            indent=2,
            default=str,
        )
    )


def cmd_flatten(_: argparse.Namespace) -> None:
    store = Store(db_path())
    broker = PaperBroker(store)
    results = broker.flatten_all(store.latest_prices())
    print(json.dumps(results, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="social-alpha paper trading research bot")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser(
        "ingest",
        help="Ingest social/news signals (offline by default; set ingest.mode=reddit when approved)",
    )
    p_ingest.set_defaults(func=cmd_ingest)

    p_prices = sub.add_parser("prices", help="Fetch prices for discovered tickers (yfinance)")
    p_prices.set_defaults(func=cmd_prices)

    p_paper = sub.add_parser("paper-once", help="Run one paper trading cycle")
    p_paper.set_defaults(func=cmd_paper_once)

    p_status = sub.add_parser("status", help="Show paper account, signals, prices")
    p_status.set_defaults(func=cmd_status)

    p_flat = sub.add_parser("flatten", help="Close all paper positions")
    p_flat.set_defaults(func=cmd_flatten)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
