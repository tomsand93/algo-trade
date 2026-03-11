# FVG Breakout

Rule-based US equities strategy built around opening-range breaks followed by Fair Value Gap retests and engulfing confirmation.

## Status

- Active strategy module
- Core logic is covered by tests
- Includes a maintained backtest entry point
- Paper and live trading code remains in `archive/` and is not part of the active surface

## Structure

```text
fvg-breakout/
|-- run_backtest.py
|-- requirements.txt
|-- src/
|   |-- analytics.py
|   |-- backtest_engine.py
|   |-- config.py
|   |-- data_fetcher.py
|   `-- pattern_detection.py
`-- tests/
```

## Strategy Rules

1. Use the 09:30-09:35 ET candle to define the daily high and low.
2. Wait for price to break above the daily high or below the daily low.
3. Detect a 3-candle Fair Value Gap after the break.
4. Require a retest into the gap.
5. Require an immediate engulfing confirmation candle.
6. Use fixed risk with a 3:1 reward-to-risk target.

## Setup

```bash
pip install -r requirements.txt
```

For Alpaca-backed data fetching, set:

```bash
ALPACA_API_KEY=your_api_key
ALPACA_API_SECRET=your_api_secret
```

You can also run fully from local CSV files.

## Run

Show usage:

```bash
python run_backtest.py --help
```

Explain the strategy rules:

```bash
python run_backtest.py --explain
```

Run a backtest using Alpaca or cached parquet data:

```bash
python run_backtest.py --symbols AAPL MSFT --start-date 2024-01-01 --end-date 2024-12-31
```

Run a backtest using local CSV files:

```bash
python run_backtest.py --use-csv --csv-dir ./csv_data --symbols AAPL
```

CSV files must be named `SYMBOL_TIMEFRAME.csv`, for example:

- `AAPL_1Min.csv`
- `AAPL_5Min.csv`

Required columns:

```text
timestamp,open,high,low,close,volume
```

## Outputs

Backtest runs can write:

- `trades_<timestamp>.csv`
- `report_<timestamp>.json`
- `equity_curve_<timestamp>.png`
- `r_distribution_<timestamp>.png`

By default, outputs go to `./results`.

## Testing

```bash
python -m pytest tests -q
python -m compileall src tests run_backtest.py
```

## Notes

- The active module is library-first plus a backtest script.
- `archive/` contains earlier experiments, reports, and paper-trading code that are preserved locally but not part of the curated repo surface.
