# Stock Screener

A modular Python stock screener for ranking equities with technical, fundamental, and optional news-based inputs.

## Overview

This module provides:

- configurable screening criteria
- ranked output using weighted scoring
- pluggable data providers
- optional Alpaca-facing bot state and broker helpers
- test coverage for criteria, broker wrapper, and state persistence

## Project Structure

```text
stock-screener/
|-- src/
|   |-- screener/      # Models, criteria evaluation, filtering
|   |-- scoring/       # Ranking algorithms
|   |-- providers/     # yfinance, OpenBB, Finnhub, FMP adapters
|   |-- broker/        # Alpaca wrapper
|   |-- bot/           # State persistence and bot support
|   |-- performance/   # Performance snapshot tracking
|   `-- utils/         # Logging and output formatting
|-- configs/           # Example YAML config
|-- scripts/           # Active CLI entry points
|-- tests/             # Unit tests
`-- archive/           # Local-only historical experiments and outputs
```

Generated outputs such as `results/`, `data/`, and archived backtest artifacts are local-only and should stay outside the curated repo surface.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

Optional providers:

- Finnhub for news enrichment
- OpenBB for fundamental data
- FMP for point-in-time historical fundamentals

## Configuration

The default configuration lives in `configs/example.yaml`.

Main sections:

- `universe`
- `criteria`
- `ranking`
- `news`
- `output`

## Usage

Run the active CLI:

```bash
python -m scripts.cli --config configs/example.yaml
```

Skip performance snapshot tracking:

```bash
python -m scripts.cli --config configs/example.yaml --no-performance-track
```

## Outputs

Depending on `output.format`, the screener can generate:

- `results.md`
- `results.csv`
- `results.json`
- run logs

These are local run artifacts and should not be committed as part of the polished repo surface.

## Testing

```bash
python -m pytest tests/
```

Verified module surfaces:

- `src/screener/`
- `src/scoring/`
- `src/broker/`
- `src/bot/`
- `scripts/cli.py`

## Notes

- `.env.example` contains placeholders only and should never hold real keys.
- The `archive/` folder contains historical scripts and outputs; the active repo-facing module lives in `src/`, `configs/`, `scripts/`, and `tests/`.

## Disclaimer

This tool produces screening results for research and workflow automation. It is not investment advice.
