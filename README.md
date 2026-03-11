# algo-trade

Standalone trading repository for active strategy code and supporting paper-trading infrastructure.

## Scope

This repository keeps the Git-facing surface focused on:

- active strategy modules under `strategies/`
- shared execution and orchestration tooling under `resources/`
- lightweight repository documentation under `docs/`

Legacy research, archived experiments, local outputs, credentials, and machine-specific files are intentionally excluded from Git through `.gitignore`.

## Active Modules

### Strategies

- `strategies/insider/`  
  SEC insider-buy signal pipeline with backtest and paper-trading entry points

- `strategies/stock-screener/`  
  Modular stock screener with ranking, provider integrations, and CLI workflow

- `strategies/orderbook/`  
  Order-book imbalance strategy with tested backtest package

- `strategies/fvg-breakout/`  
  Fair Value Gap breakout strategy with active backtest CLI

- `strategies/candlestick-pro/`  
  Candlestick-pattern strategy with live analysis, scanning, fetch, and backtest modes

### Resources

- `resources/multi-account-manager/`  
  Multi-account paper-trading manager with dashboard, persistence, and risk guardrails

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
