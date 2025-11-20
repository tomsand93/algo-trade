# Quick Start Guide

Get up and running in 5 minutes!

---

## Step 1: Installation (30 seconds)

```bash
cd crypto_backtest
pip install -r requirements.txt
```

---

## Step 2: Configure (Optional - 1 minute)

For downloading data, you need Binance API keys:

```bash
cp .env.example .env
# Edit .env and add your Binance API keys
```

**Skip this step** if you just want to test with existing data.

---

## Step 3: Quick Test (10 seconds)

Test that everything works:

```bash
python run.py help
```

You should see the help menu.

---

## Step 4: Download Data (10-15 minutes first time)

```bash
python run.py download
```

This downloads historical data for all configured assets and timeframes.

**What's happening:**
- Downloads 2 years of data (730 days)
- For 5 assets × 5 timeframes = 25 datasets
- Stores in SQLite database
- Total: ~50,000 candles

---

## Step 5: Test Single Strategy (5 seconds)

Quick test to verify everything works:

```bash
python run.py test
```

You should see results like:

```
RESULTS
======================================================================

💰 PROFITABILITY
  Initial Capital:    $   10,000.00
  Final Equity:       $   12,340.50
  Total Return:       $    2,340.50
  Total Return %:            23.41%

📊 TRADING
  Total Trades:               42
  Win Rate:                 58.5%
  Profit Factor:             1.87
```

---

## Step 6: Run Full Backtest (2-5 minutes)

Test all strategies:

```bash
python run.py backtest
```

**What's happening:**
- Tests 10 strategies
- Across 5 assets
- Across 5 timeframes
- Across 3 risk levels
- = 750 total backtests

---

## Step 7: View Results

Results are in `logs/` directory:

```bash
# Quick summary
cat logs/summary.txt

# Open Excel report
open logs/backtest_results.xlsx    # macOS
xdg-open logs/backtest_results.xlsx  # Linux
start logs/backtest_results.xlsx   # Windows
```

---

## Daily Workflow (30 seconds)

After initial setup, updating is FAST:

```bash
# Update data (only downloads new candles - 30 seconds!)
python run.py download

# Run backtests
python run.py backtest

# View results
cat logs/summary.txt
```

---

## Customization

### Test Different Strategy

Edit `test_strategy.py` (lines 17-22):

```python
STRATEGY = "MACD"              # Change this
ASSET = "ETHUSDT"              # Change this
TIMEFRAME = "4h"               # Change this
RISK = 0.20                    # Change this
```

Then:

```bash
python run.py test
```

### Add More Coins

Edit `config.py` (line 31):

```python
CRYPTO_ASSETS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",     # Add this
    "ADAUSDT",     # Add this
]
```

Then re-download:

```bash
python run.py download
```

### Add More Timeframes

Edit `config.py` (line 40):

```python
CRYPTO_INTERVALS = [
    "1m",      # Add this (lots of data!)
    "5m",
    "15m",
    "1h",
    "4h",
    "1d",
]
```

---

## Troubleshooting

### Problem: No data found

**Solution:**

```bash
python run.py download
```

### Problem: API key error

**Solution:**

Check your `.env` file has valid keys:

```bash
cat .env
```

Or download without keys (uses public endpoints).

### Problem: Module not found

**Solution:**

```bash
pip install -r requirements.txt
```

### Problem: Database locked

**Solution:**

Close other terminal windows and try again, or:

```bash
rm data/ohlcv.db
python run.py download
```

---

## Next Steps

1. ✅ Review results in `logs/summary.txt`
2. ✅ Find best performing strategies
3. ✅ Test top strategies on different timeframes
4. ✅ Adjust strategy parameters in `strategies.py`
5. ✅ Paper trade the best strategies
6. ✅ Monitor live performance

---

## Commands Cheat Sheet

```bash
# Download/update data
python run.py download              # Smart update (fast!)
python run.py download --force      # Re-download everything

# Run backtests
python run.py backtest              # All strategies
python run.py test                  # Single strategy

# Full pipeline
python run.py full                  # Download + backtest

# Info
python run.py stats                 # Database statistics
python run.py help                  # Show help
```

---

## Understanding Results

### Good Strategy Indicators:

- ✅ **Return > 20%** - Profitable
- ✅ **Sharpe > 1.5** - Good risk-adjusted returns
- ✅ **Win Rate > 55%** - More winners than losers
- ✅ **Max Drawdown < 25%** - Manageable losses
- ✅ **Profit Factor > 1.5** - Wins outweigh losses

### Red Flags:

- ❌ **Win Rate < 40%** - Too many losing trades
- ❌ **Max Drawdown > 50%** - Risky strategy
- ❌ **Few Trades (< 10)** - Not enough data
- ❌ **Negative Sharpe** - Risk not worth reward

---

## Pro Tips

1. **More data is better** - Use at least 1 year of history
2. **Test multiple timeframes** - 1h strategy may not work on 1d
3. **Watch the drawdown** - Can you handle the losses?
4. **Commission matters** - 0.1% × 100 trades = 10% cost!
5. **Paper trade first** - Test live before using real money

---

## What's Next?

Read the full [README.md](README.md) for:
- Detailed configuration options
- How to create custom strategies
- Database system details
- Performance optimization tips
- Best practices for live trading

---

**That's it! You're ready to find the best trading strategies! 🚀**

Need help? Check [README.md](README.md) or the code comments.
