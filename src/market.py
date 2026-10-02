"""Market data: yfinance primary, Schwab adapter stub for later OAuth."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import yfinance as yf

from src.config import load_config
from src.store import Store


def fetch_yfinance_quote(ticker: str) -> dict[str, Any] | None:
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d")
        if hist.empty:
            return None
        last = hist.iloc[-1]
        return {
            "ticker": ticker.upper(),
            "price": float(last["Close"]),
            "volume": float(last.get("Volume", 0) or 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "yfinance",
        }
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] yfinance failed for {ticker}: {exc}")
        return None


def passes_liquidity_filter(quote: dict[str, Any], cfg: dict[str, Any] | None = None) -> bool:
    market = (cfg or load_config())["market"]
    price = quote["price"]
    volume = quote.get("volume") or 0
    if price < market["min_price"] or price > market["max_price"]:
        return False
    if volume and volume < market["min_avg_volume"]:
        # daily volume from history can be lower intraday; keep soft for paper research
        return volume >= market["min_avg_volume"] * 0.2
    return True


def update_prices_for_tickers(store: Store, tickers: list[str]) -> dict[str, float]:
    cfg = load_config()
    prices: dict[str, float] = {}
    for ticker in sorted({t.upper() for t in tickers if t}):
        quote = fetch_yfinance_quote(ticker)
        if not quote:
            continue
        if not passes_liquidity_filter(quote, cfg):
            print(f"[INFO] Skipping {ticker}: failed liquidity/price filter")
            continue
        store.insert_price(
            ticker=quote["ticker"],
            price=quote["price"],
            ts=quote["timestamp"],
            volume=quote.get("volume"),
            source=quote["source"],
        )
        prices[quote["ticker"]] = quote["price"]
        print(f"[INFO] {ticker}: {quote['price']:.4f}")
    return prices


class SchwabMarketClient:
    """Placeholder for Schwab market data once OAuth app is approved.

    Set market.primary: schwab in config.yaml and fill SCHWAB_* env vars.
    """

    def __init__(self) -> None:
        cfg = load_config()["_env"]
        self.app_key = cfg["SCHWAB_APP_KEY"]
        self.app_secret = cfg["SCHWAB_APP_SECRET"]
        self.callback = cfg["SCHWAB_CALLBACK_URL"]
        self.token_path = cfg["SCHWAB_TOKEN_PATH"]

    def ready(self) -> bool:
        return bool(self.app_key and self.app_secret)

    def fetch_quote(self, ticker: str) -> dict[str, Any]:
        raise NotImplementedError(
            "Schwab OAuth market client not wired yet. "
            "Register an app at https://developer.schwab.com/ then we will complete auth + quotes."
        )
