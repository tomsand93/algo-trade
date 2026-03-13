# Polymarket Copy-Trade (pmirror)

Copy any public Polymarket wallet with three configurable policies. Backtest-first design — validate on historical data before committing capital.

**Status: Production-ready. 339 tests passing.**

## How It Works

### Policies

| Policy | Behaviour |
|--------|-----------|
| `mirror_latency` | Copy each trade with configurable delay (default 30s) |
| `position_rebalance` | Rebalance to match target's portfolio every N minutes |
| `fixed_allocation` | Fixed USD per copied trade |

### Finding Good Wallets
Look for: 50+ trades, win rate > 55%, profit factor > 1.5, consistent across market categories.

```bash
# Evaluate a wallet out-of-sample before copying
pmirror backtest --wallet 0x... --policy mirror_latency \
    --start 2024-01-01 --end 2025-01-01    # in-sample
pmirror backtest --wallet 0x... --policy mirror_latency \
    --start 2025-01-01 --end 2026-01-01    # out-of-sample validation
```

## Run
```bash
pip install -e .
pmirror fetch --wallet 0xYourTarget --start 2025-01-01 --end 2026-01-01
pmirror backtest --wallet 0xYourTarget --policy mirror_latency --capital 1000
pmirror report --run-id <id> --charts
```
