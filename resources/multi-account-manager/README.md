# Multi-Account Strategy Manager

Paper-trading orchestration layer for running multiple strategy adapters against separate Alpaca paper accounts, with shared state, guardrails, and an optional local dashboard.

## Status

- Active shared infrastructure module
- Main entry point: `main.py`
- Verified locally for CLI startup, report-only mode, and bytecode compilation
- Depends on local `.env` credentials for real account execution

## Structure

```text
multi-account-manager/
|-- main.py
|-- .env.example
|-- src/
|   |-- broker/
|   |-- common/
|   |-- dashboard/
|   |-- manager/
|   |-- metrics/
|   |-- storage/
|   `-- strategies/
`-- requirements.txt
```

## What It Does

- Runs multiple strategy adapters concurrently
- Keeps account and portfolio state on disk for recovery
- Applies risk guardrails such as daily loss and position limits
- Exposes a local monitoring dashboard
- Generates summary information from saved state with `--report-only`

## Setup

```powershell
cd resources/multi-account-manager
pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env` with Alpaca paper credentials only.

## Run

Show CLI usage:

```powershell
python main.py --help
```

Start the manager without the dashboard:

```powershell
python main.py --no-dashboard
```

Start the full manager with dashboard:

```powershell
python main.py
```

Generate a summary from saved local state:

```powershell
python main.py --report-only
```

Use a custom dashboard port:

```powershell
python main.py --port 9000
```

## Environment

Use [`.env.example`](C:/Users/Tom1/Desktop/TRADING/algo-trade/resources/multi-account-manager/.env.example) as the template for:

- `TRADINGVIEW_API_KEY`
- `TRADINGVIEW_API_SECRET`
- `BITCOIN4H_API_KEY`
- `BITCOIN4H_API_SECRET`
- `FVG_API_KEY`
- `FVG_API_SECRET`

## Notes

- The manager is explicitly paper-trading only.
- Local runtime state and logs are intentionally ignored from Git.
- This folder currently contains preserved local state files from previous runs; they are treated as local artifacts, not curated source files.
- `tradingView` remains an optional local-only dependency path for the adapter that references it.

## Verification

```powershell
python -m compileall src main.py
python main.py --help
python main.py --report-only
```
