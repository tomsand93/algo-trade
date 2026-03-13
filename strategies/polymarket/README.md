# Polymarket — Mean Reversion & Momentum

Two strategies for trading YES/NO tokens on Polymarket prediction markets. Supports mock, replay, backtest, paper, and live execution modes.

## Strategies

### 1. Mean Reversion

Buys YES when a market's price is unusually low relative to recent history, and buys NO when it's unusually high. Uses a rolling z-score to measure deviation.

**Signal logic:**
```
z = (price - rolling_mean(window=20)) / rolling_std(window=20)

z < -2.0  → BUY_YES   (price too low — expect reversion upward)
z > +2.0  → BUY_NO    (price too high — expect reversion downward)
Exit:  z crosses back through ±0.5
```

**Key parameters:**

| Parameter | Default |
|-----------|---------|
| Rolling window | 20 bars |
| Entry z-score | ±2.0 |
| Exit z-score | ±0.5 |
| Max position size | $10 |
| Stop loss | 20% per position |
| Daily loss limit | $50 circuit breaker |
| Cooldown per market | 5 minutes |

**Circuit breakers:** Trading halts at −5%, −10%, −15% drawdown from peak.

### 2. Momentum (Dual EMA)

Trades in the direction of short-term momentum using a dual EMA crossover on YES price.

**Signal logic:**
```
EMA_short = EMA(price, 5)
EMA_long  = EMA(price, 20)

Crossover UP   → BUY_YES
Crossover DOWN → BUY_NO
Confidence = min(|spread| × 10, 1.0)
```

## Performance Status

> **Unvalidated.** Existing backtest results ran on 3-trade fixture data only — not real historical Polymarket prices. Results show 100% win rate on 3 trades (+42.8%) which is meaningless. Needs real market data to validate.

To get real data:
```bash
python scripts/fetch_markets.py --limit 100 --days 90
```

## How Polymarket Works

Polymarket trades binary outcome contracts:
- YES token = pays $1 if event occurs, $0 if not
- NO token = pays $1 if event does not occur
- Price = implied probability (0.0–1.0)

Mean reversion assumes prediction market prices are noisy around their true probability — temporary over/under-reaction creates tradeable edges.

## Run

```bash
pip install -r requirements.txt
cp .env.example .env    # add POLYMARKET_API_KEY and PRIVATE_KEY

# Mock mode (no data needed)
python run.py --mode mock --strategy mean_reversion

# Backtest on fixture data
python run.py --mode backtest --strategy mean_reversion

# Paper trading (live data, no real money)
python run.py --mode paper --strategy mean_reversion

# Live trading
python run.py --mode live --strategy mean_reversion
```

## Files

| File | Purpose |
|------|---------|
| `polymarket_bot/strategies/mean_reversion.py` | Z-score strategy |
| `polymarket_bot/strategies/momentum.py` | Dual EMA strategy |
| `polymarket_bot/backtester.py` | Event-driven backtest engine |
| `polymarket_bot/risk.py` | Circuit breakers + position limits |
| `run.py` | Multi-mode CLI entry point |
| `data/backtest_results/` | Existing backtest outputs |
