# Candlestick Pro

Candlestick pattern strategy module with live analysis, symbol scanning, historical backtesting, and market-data fetch helpers.

## Status

- Active strategy module
- Main CLI entry point: `main.py`
- Test suite passes locally
- Archive contains older experiments, reports, and one-off backtests that are not part of the active surface

## Structure

```text
candlestick-pro/
|-- main.py
|-- requirements.txt
|-- src/
|   |-- data_fetcher.py
|   |-- indicators.py
|   |-- models.py
|   |-- patterns.py
|   |-- strategy.py
|   `-- ...
`-- tests/
```

## Install

```bash
pip install -r requirements.txt
```

## Run

Show CLI usage:

```bash
python main.py --help
```

Backtest against a local CSV file:

```bash
python main.py --mode backtest --data tests/candlestick_pro/data/obvious_engulfing.csv --pattern engulfing
```

Analyze a live market symbol:

```bash
python main.py --mode analyze --symbol BTC/USDT --pattern engulfing
```

Scan multiple symbols:

```bash
python main.py --mode scan --symbols BTC/USDT,ETH/USDT,SOL/USDT --pattern engulfing
```

Fetch and save market data:

```bash
python main.py --mode fetch --symbol BTC/USDT --output data/btc.csv
```

## Notes

- `analyze`, `scan`, and `fetch` depend on live exchange access through `ccxt`.
- `backtest` works locally with CSV input and was verified with the bundled sample dataset.
- Logs are written to `logs/trading.log`.
- The local `archive/` folder is preserved for reference but should stay outside the curated Git-facing surface.

## Verification

```bash
python -m pytest tests -q
python -m compileall src tests main.py
python main.py --help
```
