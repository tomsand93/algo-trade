# algo-trade

Standalone algorithmic trading repository focused on active strategy development, backtesting, and paper-trading infrastructure.

## Project Overview

This repository is organized as a multi-strategy trading workspace rather than a single monolithic system.

The main idea is simple:

- each strategy lives in its own self-contained module
- each module can evolve, test, and run independently
- shared operational tooling lives under `resources/`
- non-core archives, scratch research, outputs, and local credentials stay out of the Git-facing surface

The result is a cleaner repository that can function both as an active development workspace and as a presentable GitHub project.

## What This Repo Contains

- `strategies/`  
  The main strategy library. Each folder contains a focused strategy with its own code, tests, configuration, and run instructions.

- `resources/`  
  Shared infrastructure used across strategies, especially for orchestration, account management, monitoring, and paper-trading workflows.

- `docs/`  
  Lightweight repository-level notes and planning documents.

## Active Strategies

### `strategies/insider/`

Insider is an event-driven equities strategy built around SEC Form 4 insider purchase filings. It focuses on systematic extraction of open-market buy events, signal normalization, backtesting, and paper-trading workflows. Compared with the other modules, it is the most workflow-oriented strategy in the repo: data ingestion, signal generation, execution logic, and reporting are all separated into clear layers.

### `strategies/stock-screener/`

Stock Screener is a modular equity ranking system rather than a direct execution strategy. It combines configurable screening criteria, ranking logic, provider adapters, and optional performance tracking so you can score a universe of stocks before taking discretionary or automated action elsewhere. It works well as a research and idea-generation layer inside the broader repo.

### `strategies/orderbook/`

Orderbook is an L2 microstructure strategy centered on order-book state, imbalance, and short-horizon directional probability estimation. Its core trading logic is packaged more formally than most of the repo, with a tested backtest path and CLI interface. The backtest path is active; paper mode is present but currently only a stub.

### `strategies/fvg-breakout/`

FVG Breakout is a rules-based intraday equities strategy built around Fair Value Gap structure after an opening-range break. It is intentionally strict and mechanical: break, gap formation, retest, confirmation, then fixed risk management. The active module now includes a maintained backtest CLI and a tested library surface, while older experimental scripts remain outside the curated active path.

### `strategies/candlestick-pro/`

Candlestick Pro is a candlestick-pattern trading module with multiple operating modes: live analysis, symbol scanning, market-data fetching, and historical backtesting. It is more discretionary-pattern-oriented than the other strategies, with support for pattern selection, timeframe logic, and richer CLI workflows. In practice, it serves as both a strategy module and a reusable pattern-analysis engine.

## Shared Infrastructure

### `resources/multi-account-manager/`

Multi-Account Manager is the main shared orchestration layer in the repository. It is designed to run multiple strategy adapters against separate Alpaca paper accounts while tracking state, enforcing guardrails, and exposing a local dashboard. This makes it the operational glue between otherwise independent strategy modules.

## Repository Layout

```text
algo-trade/
|-- README.md
|-- .gitignore
|-- docs/
|   `-- plans/
|-- resources/
|   `-- multi-account-manager/
`-- strategies/
    |-- candlestick-pro/
    |-- fvg-breakout/
    |-- insider/
    |-- orderbook/
    `-- stock-screener/
```

## Getting Started

Each strategy is self-contained. Install dependencies and run tests from the module you want to work on.

```powershell
cd strategies/<strategy-name>
pip install -r requirements.txt
python -m pytest tests -q
```

Examples:

```powershell
cd strategies/fvg-breakout
python run_backtest.py --help
```

```powershell
cd strategies/candlestick-pro
python main.py --help
```

```powershell
cd strategies/orderbook
python -m pytest tests -q
```

For shared paper-trading orchestration:

```powershell
cd resources/multi-account-manager
copy .env.example .env
pip install -r requirements.txt
python main.py --help
```

## Verification

The active modules reviewed in this cleanup pass were verified locally through combinations of:

- `pytest`
- `compileall`
- CLI help checks
- targeted local backtest runs

## Configuration

- Use `.env.example` files as templates where provided.
- Keep real credentials in local `.env` files or environment variables only.
- Do not commit generated logs, state files, caches, result outputs, or local datasets.

## Notes

- The repository cleanup design is recorded in `docs/plans/2026-03-11-repository-curation-design.md`.
- The root CI workflow lives in `.github/workflows/ci.yml`.
