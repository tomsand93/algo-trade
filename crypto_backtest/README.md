# Crypto Trading Backtesting System

Professional-grade backtesting framework for cryptocurrency trading strategies with **smart incremental updates** and comprehensive performance analysis.

## ✨ Key Features

- **🚀 10 Trading Strategies** - RSI, MACD, Bollinger Bands, SMA/EMA Crossover, Mean Reversion, Momentum, VWAP, Breakout, Triple EMA
- **💾 Smart Database** - SQLite with incremental updates (only downloads NEW candles!)
- **📊 All Timeframes** - 5m, 15m, 1h, 4h, 1d (No Lumibot limitations!)
- **⚡ Fast Updates** - First download: 10-15 min | Future updates: 30 seconds
- **📈 Comprehensive Metrics** - Sharpe, Sortino, Max Drawdown, Win Rate, Profit Factor
- **💰 Realistic Simulation** - Commission (0.1%), slippage (0.05%), proper position sizing
- **📊 Excel Reports** - Detailed analysis with multiple sheets
- **🎯 Multi-dimensional Testing** - Test across assets, timeframes, and risk levels

---

## 🚀 Quick Start (5 Minutes)

### 1. Installation

```bash
cd crypto_backtest
pip install -r requirements.txt
```

### 2. Configure API Keys (Optional for backtesting)

```bash
cp .env.example .env
# Edit .env and add your Binance API keys
```

**Note**: For backtesting only, you don't need API keys if you're downloading data manually.

### 3. Download Data

```bash
# First time download (10-15 minutes)
python run.py download
```

### 4. Run Backtests

```bash
# Run all strategies across all configurations
python run.py backtest
```

### 5. View Results

Results are saved to `logs/`:
- `backtest_results.xlsx` - Full Excel report
- `summary.txt` - Quick text summary
- `backtest_results.json` - Machine-readable data

---

## 📋 Usage Commands

```bash
# Download/update data
python run.py download              # Smart incremental update
python run.py download --force      # Force re-download everything

# Run backtests
python run.py backtest              # Test all strategies

# Full pipeline
python run.py full                  # Download + backtest

# View database info
python run.py stats                 # Show database statistics

# Quick test
python run.py test                  # Test single strategy

# Help
python run.py help                  # Show all commands
```

---

## 💡 Daily Workflow

```bash
# Morning: Update data (30 seconds - only new candles!)
python run.py download

# Run backtests with fresh data
python run.py backtest

# View results
cat logs/summary.txt
open logs/backtest_results.xlsx
```

---

## 🎯 10 Trading Strategies

All strategies are battle-tested and include proper indicator calculations:

1. **RSI** - Relative Strength Index (oversold/overbought)
2. **MACD** - Moving Average Convergence Divergence crossovers
3. **BOLLINGER_BANDS** - Mean reversion at upper/lower bands
4. **SMA_CROSSOVER** - Simple Moving Average (50/200 Golden/Death Cross)
5. **EMA_CROSSOVER** - Exponential Moving Average (12/26)
6. **MEAN_REVERSION** - Statistical mean reversion with std dev
7. **MOMENTUM** - Price momentum strategy
8. **VWAP** - Volume Weighted Average Price crossovers
9. **BREAKOUT** - Support/resistance breakouts
10. **TRIPLE_EMA** - Triple EMA alignment (9/21/55)

---

## 📊 Performance Metrics

Each backtest calculates:

- **Returns** - Total return, return %
- **Risk-Adjusted** - Sharpe ratio, Sortino ratio
- **Drawdown** - Maximum drawdown, maximum drawdown %
- **Trade Stats** - Win rate, profit factor, avg win/loss
- **Best/Worst** - Best trade, worst trade
- **Costs** - Total commission paid
- **Duration** - Average trade duration

---

## 🔧 Configuration

Edit `config.py` to customize:

```python
# Trading pairs
CRYPTO_ASSETS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]

# Timeframes
CRYPTO_INTERVALS = ["5m", "15m", "1h", "4h", "1d"]

# Position sizing
RISK_LEVELS = [0.05, 0.10, 0.20]  # 5%, 10%, 20%

# Capital
INITIAL_CAPITAL = 10000

# Costs
COMMISSION = 0.001  # 0.1% Binance fee
SLIPPAGE = 0.0005   # 0.05% slippage

# Data freshness
MAX_DATA_AGE_HOURS = 1  # Update if older than 1 hour
```

---

## 💾 Smart Database System

### How It Works

The system uses SQLite to store OHLCV data and **only downloads new candles**:

```python
# First download
python run.py download
# Downloads: BTC 1h from 2023-01-01 to 2024-11-20 (730 days = 17,520 candles)

# Next day
python run.py download
# Downloads: BTC 1h from 2024-11-20 to 2024-11-21 (24 new candles only!)
```

### Benefits

- ⚡ **100x faster updates** - Incremental downloads
- 💾 **Smaller storage** - Compressed database
- 🔍 **Fast queries** - SQLite indexing
- 📊 **Metadata tracking** - Know when data was last updated
- 🔄 **Auto-freshness** - Updates automatically if stale

### Database Commands

```bash
# View database statistics
python run.py stats

# Force refresh all data
python run.py download --force

# Access database programmatically
python
>>> from database import OHLCVDatabase
>>> db = OHLCVDatabase()
>>> df = db.load_ohlcv('BTC/USDT', '1h')
>>> print(df.head())
```

---

## 🧪 Testing Individual Strategies

Edit `test_strategy.py` (lines 17-22):

```python
STRATEGY = "MACD"              # Try different strategies
ASSET = "ETHUSDT"              # Try different coins
TIMEFRAME = "4h"               # Try different timeframes
RISK = 0.20                    # Try different risk levels
```

Then run:

```bash
python run.py test
```

---

## 📈 Example Results

After running backtests, you'll get output like:

```
TOP 10 PERFORMERS
----------------------------------------------------------------------

#1
  Strategy: MACD
  Asset: BTCUSDT
  Timeframe: 4h
  Risk: 10%
  Return: 127.5%
  Sharpe: 2.34
  Win Rate: 62.5%
  Max DD: -15.2%
  Trades: 42

#2
  Strategy: TRIPLE_EMA
  Asset: ETHUSDT
  Timeframe: 1h
  Risk: 20%
  Return: 98.3%
  Sharpe: 1.87
  Win Rate: 58.3%
  Max DD: -22.1%
  Trades: 67
```

---

## 🎨 Customization

### Add Your Own Strategy

Edit `strategies.py`:

```python
def my_custom_strategy(df):
    """
    Your strategy logic

    Returns:
        1 = BUY
       -1 = SELL
        0 = HOLD
    """
    # Your logic here
    if buy_condition:
        return 1
    elif sell_condition:
        return -1
    return 0

# Add to registry
STRATEGIES["MY_STRATEGY"] = my_custom_strategy
```

Then add to `config.py`:

```python
STRATEGIES = [
    "RSI",
    "MACD",
    "MY_STRATEGY",  # Your new strategy
]
```

### Add More Assets

Edit `config.py`:

```python
CRYPTO_ASSETS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",     # Add Solana
    "ADAUSDT",     # Add Cardano
    "DOGEUSDT",    # Add Dogecoin
    "XRPUSDT",     # Add Ripple
]
```

### Add More Timeframes

Edit `config.py`:

```python
CRYPTO_INTERVALS = [
    "1m",      # 1 minute (lots of data!)
    "5m",      # 5 minutes
    "15m",     # 15 minutes
    "1h",      # 1 hour
    "4h",      # 4 hours
    "1d",      # 1 day
    "1w",      # 1 week
]
```

---

## 📁 Project Structure

```
crypto_backtest/
├── config.py                  # Configuration settings
├── database.py                # SQLite database manager
├── data_fetcher.py            # Smart data downloader
├── strategies.py              # 10 trading strategies
├── backtest_engine.py         # Backtesting engine
├── evaluator.py               # Runs all backtests
├── run.py                     # Main runner
├── test_strategy.py           # Quick strategy tester
├── requirements.txt           # Python dependencies
├── .env.example               # API key template
├── .gitignore                 # Git ignore rules
├── README.md                  # This file
├── QUICKSTART.md              # 5-minute guide
│
├── data/                      # Created at runtime
│   └── ohlcv.db               # SQLite database
│
└── logs/                      # Created at runtime
    ├── backtest_results.xlsx
    ├── backtest_results.json
    └── summary.txt
```

---

## ⚠️ Important Notes

### Security

- **Never commit .env file** - Contains API keys
- **API keys are optional** - Only needed for downloading data
- **Use testnet first** - Test with testnet before live keys

### Performance

- **Past performance ≠ future results** - Backtests don't guarantee profits
- **Commission matters** - 0.1% per trade adds up quickly
- **Slippage happens** - Real execution differs from backtest
- **Market conditions change** - Strategies may not work in all markets

### Best Practices

1. **Test multiple timeframes** - What works on 1h may fail on 1d
2. **Check drawdown** - Can you handle the worst losses?
3. **Validate on multiple assets** - BTC ≠ altcoins
4. **Paper trade first** - Test live before using real money
5. **Monitor performance** - Re-evaluate strategies regularly

---

## 🐛 Troubleshooting

### No data found

```bash
# Download data first
python run.py download
```

### API key error

```bash
# Check .env file exists
ls -la .env

# Verify keys are set
cat .env

# Or download without keys (limited)
python run.py download
```

### Module not found

```bash
# Install dependencies
pip install -r requirements.txt
```

### Database locked

```bash
# Close other processes using database
# Or delete and re-download
rm data/ohlcv.db
python run.py download
```

---

## 📚 Additional Resources

- [QUICKSTART.md](QUICKSTART.md) - 5-minute setup guide
- [Binance API Docs](https://binance-docs.github.io/apidocs/spot/en/)
- [CCXT Documentation](https://docs.ccxt.com/)
- [Backtrader Docs](https://www.backtrader.com/docu/)

---

## 🤝 Contributing

Contributions welcome! Some ideas:

- Add more strategies
- Improve performance metrics
- Add machine learning strategies
- Create web dashboard
- Add live trading capability
- Implement walk-forward optimization

---

## 📄 License

MIT License - Use at your own risk

---

## ⚠️ Disclaimer

This software is for educational and research purposes only. Cryptocurrency trading carries significant risk. You can lose all your capital. Never trade with money you can't afford to lose. Always do your own research and consider consulting with a financial advisor. Past performance does not guarantee future results.

---

## 🎯 Getting Started Checklist

- [ ] Install dependencies (`pip install -r requirements.txt`)
- [ ] Configure API keys (optional, copy `.env.example` to `.env`)
- [ ] Download data (`python run.py download`)
- [ ] Run quick test (`python run.py test`)
- [ ] Run full backtest (`python run.py backtest`)
- [ ] Analyze results (`logs/summary.txt`)
- [ ] Test top strategies with paper trading
- [ ] Monitor live performance

---

**Happy Backtesting! 🚀**
