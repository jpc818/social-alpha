"""Paper broker with PDT-aware risk guards for a $1k sim account."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from src.config import load_config
from src.store import Store


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class RiskGuard:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg["paper"]

    def day_trade_count(self, day_trades: list[str]) -> int:
        # Count unique session dates in rolling window conceptually tracked as list of dates
        return len(day_trades)

    def can_open(
        self,
        account: dict[str, Any],
        positions: dict[str, dict[str, Any]],
        ticker: str,
        is_day_trade: bool,
    ) -> tuple[bool, str]:
        if len(positions) >= int(self.cfg["max_open_positions"]) and ticker not in positions:
            return False, "max_open_positions"
        if is_day_trade and self.day_trade_count(account["day_trades"]) >= int(
            self.cfg["max_day_trades_per_5_sessions"]
        ):
            return False, "pdt_day_trade_limit"
        start = float(account["starting_cash"])
        equity = float(account["equity"])
        if start > 0 and (start - equity) / start >= float(self.cfg["daily_loss_limit_pct"]):
            return False, "daily_loss_limit"
        return True, "ok"


class PaperBroker:
    def __init__(self, store: Store):
        self.store = store
        self.cfg = load_config()
        paper = self.cfg["paper"]
        self.store.ensure_paper_account(float(paper["starting_cash"]))
        self.risk = RiskGuard(self.cfg)

    def _apply_costs(self, price: float, side: str) -> float:
        paper = self.cfg["paper"]
        bps = (float(paper["slippage_bps"]) + float(paper["spread_bps"])) / 10000.0
        if side == "BUY":
            return price * (1 + bps)
        return price * (1 - bps)

    def mark_to_market(self, prices: dict[str, float]) -> float:
        account = self.store.get_paper_account()
        positions = self.store.get_positions()
        equity = float(account["cash"])
        for ticker, pos in positions.items():
            px = prices.get(ticker)
            if px is None:
                px = float(pos["avg_price"])
            equity += float(pos["qty"]) * float(px)
        self.store.save_paper_account(float(account["cash"]), equity, account["day_trades"])
        return equity

    def buy(self, ticker: str, price: float, reason: str = "") -> dict[str, Any]:
        ticker = ticker.upper()
        account = self.store.get_paper_account()
        positions = self.store.get_positions()
        ok, why = self.risk.can_open(account, positions, ticker, is_day_trade=False)
        if not ok:
            self.store.record_order(ticker, "BUY", 0, price, "REJECTED", why)
            return {"status": "REJECTED", "reason": why}

        fill = self._apply_costs(price, "BUY")
        max_notional = float(account["equity"]) * float(self.cfg["paper"]["max_position_pct"])
        cash = float(account["cash"])
        notional = min(max_notional, cash)
        if notional < fill:
            self.store.record_order(ticker, "BUY", 0, fill, "REJECTED", "insufficient_cash")
            return {"status": "REJECTED", "reason": "insufficient_cash"}

        qty = notional / fill
        existing = positions.get(ticker)
        if existing:
            new_qty = float(existing["qty"]) + qty
            new_avg = (
                float(existing["qty"]) * float(existing["avg_price"]) + qty * fill
            ) / new_qty
            self.store.upsert_position(ticker, new_qty, new_avg, existing["opened_at"])
        else:
            self.store.upsert_position(ticker, qty, fill)

        new_cash = cash - qty * fill
        self.store.save_paper_account(new_cash, float(account["equity"]), account["day_trades"])
        self.store.record_order(ticker, "BUY", qty, fill, "FILLED", reason)
        self.mark_to_market({ticker: price})
        return {"status": "FILLED", "side": "BUY", "ticker": ticker, "qty": qty, "price": fill}

    def sell(self, ticker: str, price: float, reason: str = "", qty: float | None = None) -> dict[str, Any]:
        ticker = ticker.upper()
        account = self.store.get_paper_account()
        positions = self.store.get_positions()
        pos = positions.get(ticker)
        if not pos:
            self.store.record_order(ticker, "SELL", 0, price, "REJECTED", "no_position")
            return {"status": "REJECTED", "reason": "no_position"}

        sell_qty = float(pos["qty"]) if qty is None else min(float(qty), float(pos["qty"]))
        fill = self._apply_costs(price, "SELL")

        opened_day = str(pos["opened_at"])[:10]
        is_day_trade = opened_day == _today()
        if is_day_trade:
            ok, why = self.risk.can_open(account, positions, ticker, is_day_trade=True)
            if not ok and why == "pdt_day_trade_limit":
                self.store.record_order(ticker, "SELL", 0, fill, "REJECTED", why)
                return {"status": "REJECTED", "reason": why}

        proceeds = sell_qty * fill
        remaining = float(pos["qty"]) - sell_qty
        self.store.upsert_position(ticker, remaining, float(pos["avg_price"]), pos["opened_at"])
        day_trades = list(account["day_trades"])
        if is_day_trade:
            day_trades.append(_today())
            # keep last 5 session markers
            day_trades = day_trades[-5:]

        new_cash = float(account["cash"]) + proceeds
        self.store.save_paper_account(new_cash, float(account["equity"]), day_trades)
        self.store.record_order(ticker, "SELL", sell_qty, fill, "FILLED", reason, day_trade=is_day_trade)
        self.mark_to_market({ticker: price})
        return {
            "status": "FILLED",
            "side": "SELL",
            "ticker": ticker,
            "qty": sell_qty,
            "price": fill,
            "day_trade": is_day_trade,
        }

    def flatten_all(self, prices: dict[str, float], reason: str = "eod_flatten") -> list[dict[str, Any]]:
        results = []
        for ticker, pos in list(self.store.get_positions().items()):
            px = prices.get(ticker, float(pos["avg_price"]))
            results.append(self.sell(ticker, px, reason=reason))
        return results

    def summary(self) -> dict[str, Any]:
        account = self.store.get_paper_account()
        positions = self.store.get_positions()
        return {
            "cash": account["cash"],
            "equity": account["equity"],
            "starting_cash": account["starting_cash"],
            "day_trades": account["day_trades"],
            "positions": positions,
            "recent_orders": self.store.recent_orders(20),
        }
