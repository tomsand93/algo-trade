# Orderbook Strategy

L2 orderbook trading strategy with distribution-based directional probability estimation.

## Overview

Core sequence:

`Liquidity Sweep -> Absorption -> Imbalance Flip -> Retest Entry`

The strategy estimates directional probability from recent orderbook and trade flow state, then uses a probability gate before entering.

## Project Structure

```text
orderbook/
|-- src/orderbook_strategy/   # Strategy, backtest, config, reporting, CLI
|-- tests/                    # Unit tests
|-- config.yaml               # Default strategy configuration
|-- pyproject.toml            # Packaging and pytest config
`-- archive/                  # Local-only experiments, datasets, and prior outputs
```

Archived configs, sample datasets, and generated outputs are local-only materials and should not be treated as the active tracked surface.

## Installation

Editable install:

```bash
pip install -e .
```

Or run directly with `PYTHONPATH=src`.

## Backtest

Installed package form:

```bash
orderbook-backtest backtest \
  --trades archive/data/sample_trades.csv \
  --book archive/data/sample_orderbook.csv \
  --config config.yaml
```

Direct module form:

```bash
PYTHONPATH=src python -m orderbook_strategy.cli backtest \
  --trades archive/data/sample_trades.csv \
  --book archive/data/sample_orderbook.csv \
  --config config.yaml
```

## Paper Mode

```bash
PYTHONPATH=src python -m orderbook_strategy.cli paper \
  --trades archive/data/sample_trades.csv \
  --book archive/data/sample_orderbook.csv \
  --config config.yaml
```

Current status: paper mode is a stub and logs that streaming/live simulation is not yet implemented.

## Data Format

Trades CSV:

```csv
timestamp,price,size,side
2024-01-01T10:00:00.000Z,43250.5,0.5,buy
2024-01-01T10:00:00.250Z,43251.0,1.2,sell
```

Orderbook CSV:

```csv
timestamp,side,level,price,size
2024-01-01T10:00:00.000Z,bid,0,43249.5,2.5
2024-01-01T10:00:00.000Z,ask,0,43250.5,1.8
```

## Fill Assumptions

- latency via `latency_ms`
- slippage via `slippage_ticks`
- conservative execution for entries and exits
- commission via `fee_per_share_or_contract`

## Probability Model

The distribution is built with a no-lookahead workflow:

1. realized returns are only added after the horizon has elapsed
2. distributions are keyed by state
3. entries require probability threshold confirmation

Supported distribution types:

- `normal`
- `hist`

## Outputs

Backtests write local outputs such as:

- `trades.csv`
- `equity.csv`
- `summary.json`
- `equity.png`

These are local run artifacts and should not be committed as part of the curated repo surface.

## Testing

```bash
python -m pytest tests/
```

## Status

- Backtest path: implemented
- CLI: implemented
- Paper mode: stub

## Limitations

- queue position is not modeled
- market impact is not modeled
- output quality depends on orderbook snapshot quality and frequency

## Disclaimer

This strategy is for research and simulation use. Execution in live markets may differ materially from backtest assumptions.
