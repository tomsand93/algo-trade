# algo-trade

Curated trading research repository focused on active strategy code and supporting infrastructure.

## What Is In Scope

- `strategies/`: active strategy modules with their own code, tests, and documentation
- `resources/multi-account-manager/`: orchestration layer for running multiple strategies on separate paper accounts
- `docs/`: repository-facing notes and plans

Non-core local folders such as old archives, research scratch space, and legacy strategy bundles are preserved on disk but are not intended to be part of the Git-facing repository.

## Active Modules

### Strategies

- `strategies/candlestick-pro/`: BTC/USD candlestick-pattern strategy
- `strategies/fvg-breakout/`: fair-value-gap breakout strategy
- `strategies/insider/`: insider-buy signal pipeline from SEC filings to execution
- `strategies/orderbook/`: order-book imbalance strategy
- `strategies/stock-screener/`: modular stock screener with ranking and optional news enrichment

### Infrastructure

- `resources/multi-account-manager/`: async manager, dashboard, persistence, and risk guardrails for running multiple paper-trading accounts

## Repository Layout

```text
algo-trade/
|-- README.md
|-- .gitignore
|-- docs/
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

Each strategy is currently self-contained and manages its own dependencies.

```powershell
cd strategies/<strategy-name>
pip install -r requirements.txt
python -m pytest tests -q
```

Examples:

- `strategies/insider/`
- `strategies/fvg-breakout/`
- `strategies/candlestick-pro/`
- `strategies/orderbook/`
- `strategies/stock-screener/`

For the orchestration layer:

```powershell
cd resources/multi-account-manager
copy .env.example .env
pip install -r requirements.txt
python main.py --no-dashboard
```

## Configuration

- Use environment variables or local `.env` files for credentials.
- Do not commit real API keys, SMTP passwords, or local machine paths.
- Local-only data, logs, results, and legacy folders are excluded through `.gitignore`.

## Notes

- `docs/plans/2026-03-11-repository-curation-design.md` records the cleanup design used for this repository pass.
- The current CI workflow lives in `.github/workflows/ci.yml` and covers several active strategy modules.
