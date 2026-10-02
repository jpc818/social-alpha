# social-alpha

Fork of [Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis](https://github.com/fsaavedra0003/Agentic-AI-Trading-Bot-with-LLM-reasoning-sentiment-analysis), iterated for **meme-stock social sentiment research** and a **$1,000 paper day-trading simulator**.

**Live Schwab order placement is disabled.** Market data can move to Schwab after OAuth setup; execution stays paper until you explicitly unlock it later.

This is an experiment harness, not investment advice.

## What works now

- **Offline ingest (default):** seed meme tickers + bundled sample Reddit/news JSON + optional NewsAPI
- Reddit live ingest available when `ingest.mode: reddit` and you have API approval (Reddit blocked new self-serve apps)
- VADER sentiment + `$TICKER` extraction (optional OpenAI)
- SQLite storage for mentions, prices, paper orders
- yfinance quotes with liquidity/price filters
- Paper broker with PDT-aware limits (max 3 day trades / 5 sessions), position sizing, daily loss kill-switch
- CLI: `ingest` → `prices` → `paper-once` → `status`

## What is not done yet

- Wired Schwab OAuth market-data client (stub in `src/market.py`)
- Correlation research notebooks / holdout evaluation
- X/Twitter live polling (adapter exists upstream; API is paid — off by default)
- Streamlit dashboard / live broker execution

## Setup

1. Python 3.12+
2. Create a virtualenv and install deps:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

3. Copy env template:

```bash
copy .env.example .env
```

Reddit credentials are **optional** until Reddit approves API access (Responsible Builder Policy). Offline mode runs without them.

4. Optional: `NEWS_API_KEY`, OpenAI, Schwab developer app, X bearer token.

## Usage

```bash
python main.py ingest
python main.py prices
python main.py paper-once
python main.py status
python main.py flatten
```

Config lives in `config.yaml` (cash, PDT limits, subreddits, filters).

## Safety

- `LIVE_TRADING=false` in `.env` — keep it that way
- Paper account starts at `$1000` with max ~20% per position and EOD flatten helper
- Under $25k, real PDT rules would restrict frequent day trades; the paper engine mirrors that

## Upstream

- `origin` → https://github.com/jpc818/social-alpha
- `upstream` → original portfolio repo (ingestion / sentiment / xgboost sketches retained under `ingestion/`, `sentiment/`, `models/`)
