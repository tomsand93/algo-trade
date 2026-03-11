# Insider Buy Signal Trading System

A reproducible Python strategy built around single insider-buy events from SEC Form 4 filings, with both backtesting and paper-trading workflows.

## Overview

This module turns insider purchase filings into systematic trade signals with:

- Open-market purchase filtering
- Single-buyer signal rules
- Minimum dollar-threshold filtering
- Bracket exits for risk control
- Backtest reporting and paper-trading support

## Project Structure

```text
insider/
|-- src/
|   |-- data/           # SEC API client, price provider
|   |-- normalize/      # Form 4 parser and schemas
|   |-- signals/        # Signal generation rules
|   |-- backtest/       # Backtest engine, execution, portfolio
|   |-- live/           # Paper trading, scheduling, risk checks
|   `-- reports/        # Metrics and plotting
|-- configs/            # config.yaml, example.env
|-- scripts/            # run, download, debug, and inspection helpers
|-- tests/              # Unit tests
`-- archive/            # Local-only outputs, caches, and prior runs
```

Generated working data such as `data/`, `logs/`, and `results/` is created locally during runs and should not be treated as core tracked source.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

Copy `configs/example.env` to `.env`:

```bash
cp configs/example.env .env
```

Then set:

```bash
SEC_API_KEY=your_sec_api_key_here
ALPACA_API_KEY=your_alpaca_paper_api_key
ALPACA_API_SECRET=your_alpaca_paper_api_secret
PAPER_MODE=true
```

### 3. API providers

- SEC insider data: https://sec-api.io/
- Alpaca paper trading: https://alpaca.markets/

## Main Workflows

### Download insider data

```bash
python scripts/download_insiders.py --lookback 365 --output data/insider_transactions.json
```

Or with an explicit range:

```bash
python scripts/download_insiders.py --start 2023-01-01 --end 2024-12-31
```

### Run a backtest

```bash
python scripts/run_backtest.py \
    --data data/insider_transactions.json \
    --start 2023-01-01 \
    --end 2024-12-31 \
    --output results/backtest_2024
```

### Run a parameter sweep

```bash
python scripts/run_backtest.py --sweep \
    --data data/insider_transactions.json \
    --start 2023-01-01 \
    --end 2024-12-31 \
    --output results/sweep
```

Quick sweep:

```bash
python scripts/run_backtest.py --sweep --quick \
    --data data/insider_transactions.json \
    --start 2023-01-01 \
    --end 2024-12-31
```

### Run paper trading

Dry run:

```bash
python scripts/run_paper.py --dry-run --once
```

Continuous paper run:

```bash
python scripts/run_paper.py
```

## Script Guide

- `download_insiders.py`, `download_multi_ticker.py`: fetch and cache insider data
- `run_backtest.py`: backtest and parameter sweep entry point
- `run_paper.py`, `run_paper_dryrun.py`, `run_live_paper.py`: paper-trading entry points
- `show_*.py`, `check_orders.py`: operational inspection helpers
- `debug_*.py`, `test_*.py`, `simple_download.py`, `quick_download.py`: development helpers useful locally but not the main public entry points

## Configuration

Main strategy and execution settings live in `configs/config.yaml`.

Key settings include:

- `threshold_usd`
- `min_dvol`
- `position_size_pct`
- `max_positions`
- `stop_loss_pct`
- `take_profit_pct`
- `max_hold_bars`

## Signal Rules

The strategy applies these core rules:

1. Open-market buys only (`transaction_code == "P"`)
2. Acquisition-only events
3. Exactly one qualifying buy per ticker per date
4. Minimum dollar threshold
5. Optional liquidity filtering

## Backtest Outputs

Typical local outputs include:

- `results.json`
- summary text files
- equity and drawdown plots
- parameter-sweep CSV output

These artifacts are local run outputs and should stay out of the curated repository surface.

## Testing

```bash
python -m pytest tests/
```

Primary repo-facing entry points:

- Backtest: `python scripts/run_backtest.py ...`
- Paper trading: `python scripts/run_paper.py ...`
- Tests: `python -m pytest tests/`

## Safety Notes

- Use paper credentials only.
- Keep `PAPER_MODE=true`.
- Do not commit real `.env` files.
- Verify orders and positions regularly when running the bot.

## License

MIT. See `LICENSE`.

## Disclaimer

This software is for research and educational use. Trading involves real risk, and you are responsible for your own decisions and outcomes.
