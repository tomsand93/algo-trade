# Quick Start Guide

Get up and running in 5 minutes!

## Step 1: Install Dependencies

```bash
cd ALGOV2
pip install -r requirements.txt
```

## Step 2: Configure API Keys (Optional for backtesting)

For downloading fresh data, you'll need Binance API keys:

1. Copy `.env.example` to `.env`
2. Add your Binance API keys
3. Or use the keys already in `config.py` (testnet keys provided)

**Note**: For backtesting only (not downloading new data), you can skip this step if data is already downloaded.

## Step 3: Test Single Strategy

Test one strategy quickly to ensure everything works:

```bash
python test_single.py
```

This will run the RSI strategy on BTC/USDT 1h timeframe and show results in ~10 seconds.

## Step 4: Download Historical Data

Download data for all configured assets and timeframes:

```bash
python run.py download
```

This will take 5-15 minutes depending on your internet connection.

## Step 5: Run Full Backtest

Run all strategies on all assets and timeframes:

```bash
python run.py backtest
```

This will take 2-5 minutes and test hundreds of combinations.

## Step 6: View Results

Check the `logs/` directory for:

- `backtest_results.xlsx` - Detailed Excel report
- `summary.txt` - Quick text summary
- `backtest_results.json` - Data for custom analysis

## Step 7: Visualize Results (Optional)

Generate charts and graphs:

```bash
python visualize_results.py
```

## Customization

### Test Different Strategy Parameters

Edit `test_single.py` lines 15-19:

```python
STRATEGY = "MACD"              # Try: RSI, MACD, BOLLINGER_BANDS, etc.
ASSET = "ETHUSDT"              # Try: BTCUSDT, ETHUSDT, BNBUSDT
TIMEFRAME = "4h"               # Try: 15m, 1h, 4h, 1d
RISK = 0.20                    # Try: 0.05, 0.10, 0.20
```

### Add More Assets

Edit `config.py`:

```python
CRYPTO_ASSETS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",    # Add Solana
    "ADAUSDT",    # Add Cardano
    # Add any Binance pair
]
```

### Add More Timeframes

Edit `config.py`:

```python
CRYPTO_INTERVALS = [
    "5m",      # Add 5 minute
    "15m",
    "1h",
    "4h",
    "1d",
]
```

## Troubleshooting

### No data found error

Run `python run.py download` first to fetch historical data.

### API key error

- Check your API keys in `.env` or `config.py`
- Make sure API keys have permission to read market data
- Or use the provided testnet keys

### ModuleNotFoundError

Run `pip install -r requirements.txt` again.

### Empty results

- Ensure data has enough candles (minimum 300)
- Check if the asset/timeframe combination exists on Binance
- Try a longer lookback period in `config.py`

## Next Steps

1. Review top performers in `logs/summary.txt`
2. Analyze best strategy/asset/timeframe combinations
3. Fine-tune strategy parameters in `strategies_advanced.py`
4. Test on different market conditions (bear market, bull market, sideways)
5. Consider paper trading the best strategies

## Warning

⚠️ **Backtests show historical performance only. Past performance does NOT guarantee future results.**

Always paper trade before using real money!

## Support

- Read `README.md` for detailed documentation
- Check strategy code in `strategies_advanced.py`
- Review backtest engine in `backtester.py`
- Examine configuration in `config.py`
