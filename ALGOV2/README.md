# Advanced Crypto Trading Backtesting Framework

A comprehensive backtesting framework for cryptocurrency trading strategies using Binance data.

## Features

- ✅ **Multiple Timeframes**: 1m, 5m, 15m, 1h, 2h, 4h, 1d
- ✅ **10 Trading Strategies**: RSI, MACD, Bollinger Bands, SMA/EMA Crossover, Mean Reversion, Momentum, VWAP, Breakout, Triple EMA
- ✅ **Real Binance Data**: Using CCXT library for accurate historical data
- ✅ **Comprehensive Metrics**: Sharpe ratio, Sortino ratio, Max Drawdown, Win Rate, Profit Factor
- ✅ **Commission & Slippage**: Realistic trading costs included
- ✅ **Multiple Risk Levels**: Test 5%, 10%, 20% position sizing
- ✅ **Excel Reports**: Detailed performance analysis and comparisons

## Strategies Included

1. **RSI** - Relative Strength Index (oversold/overbought)
2. **MACD** - Moving Average Convergence Divergence
3. **BOLLINGER_BANDS** - Price mean reversion using Bollinger Bands
4. **SMA_CROSSOVER** - Simple Moving Average crossover (50/200)
5. **EMA_CROSSOVER** - Exponential Moving Average crossover (12/26)
6. **MEAN_REVERSION** - Statistical mean reversion
7. **MOMENTUM** - Price momentum strategy
8. **VWAP** - Volume Weighted Average Price
9. **BREAKOUT** - Support/resistance breakout
10. **TRIPLE_EMA** - Triple EMA alignment strategy

## Installation

```bash
cd ALGOV2
pip install -r requirements.txt
```

## Configuration

Edit `config.py` to customize:

- **Assets**: Which cryptocurrencies to test (BTC, ETH, BNB, etc.)
- **Timeframes**: Which intervals to test
- **Risk Levels**: Position sizing (5%, 10%, 20%)
- **Lookback Period**: How much historical data to use
- **Initial Capital**: Starting balance for backtests

⚠️ **IMPORTANT**: Update your API keys in `config.py` or use environment variables

## Usage

### 1. Download Data from Binance

```bash
python run.py download
```

This will download historical OHLCV data for all configured assets and timeframes.

### 2. Run Backtests

```bash
python run.py backtest
```

This will:
- Run all strategies on all assets/timeframes/risk levels
- Generate comprehensive performance metrics
- Save results to Excel and JSON

### 3. Full Pipeline (Download + Backtest)

```bash
python run.py full
```

### Quick Test (Single Strategy)

```bash
python test_single.py
```

## Output Files

All results are saved to the `logs/` directory:

- **backtest_results.xlsx** - Full results with multiple sheets:
  - All Results - Complete data
  - Top 50 by Return - Best performers
  - Top 50 by Sharpe - Best risk-adjusted returns
  - Strategy Summary - Performance by strategy
  - Asset Summary - Performance by asset
  - Timeframe Summary - Performance by timeframe
  - Risk Summary - Performance by risk level

- **summary.txt** - Human-readable summary with top performers

- **backtest_results.json** - Machine-readable results for further analysis

## Performance Metrics

Each backtest includes:

- **Total Return %** - Overall profit/loss
- **Sharpe Ratio** - Risk-adjusted return
- **Sortino Ratio** - Downside risk-adjusted return
- **Max Drawdown** - Largest peak-to-trough decline
- **Win Rate** - Percentage of profitable trades
- **Profit Factor** - Gross profit / Gross loss
- **Avg Win/Loss** - Average winning and losing trade sizes
- **Number of Trades** - Total trades executed
- **Total Commission** - Trading fees paid

## Example Results

After running backtests, you'll see:

```
TOP PERFORMER:
Strategy: MACD
Asset: BTCUSDT
Timeframe: 4h
Risk: 10%
Return: +127.5%
Sharpe Ratio: 2.34
Win Rate: 62.5%
Max Drawdown: -15.2%
```

## Customization

### Add Your Own Strategy

Edit `strategies_advanced.py`:

```python
def my_custom_strategy(df):
    """
    Your strategy logic
    Returns: 1 (buy), -1 (sell), 0 (hold)
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

### Test Different Parameters

Modify strategy parameters in `strategies_advanced.py`:
- RSI periods (default: 14)
- MACD fast/slow/signal (default: 12/26/9)
- Bollinger Band periods (default: 20)
- Moving average periods

## Tips for Best Results

1. **More data is better** - Use at least 180 days of history
2. **Consider commission** - 0.1% per trade adds up quickly
3. **Watch the Sharpe ratio** - High returns with low risk is ideal
4. **Check max drawdown** - Ensure you can tolerate the worst losses
5. **Validate on multiple assets** - A strategy that works on BTC may fail on altcoins
6. **Test multiple timeframes** - What works on 1h may not work on 1d

## Limitations

- **Past performance ≠ Future results** - Backtests don't guarantee live trading success
- **No order book simulation** - Assumes all orders fill at close price
- **No market impact** - Assumes your trades don't move the market
- **Slippage is estimated** - Real slippage may vary
- **No partial fills** - All trades are assumed to fill completely

## Roadmap

- [ ] Add more strategies (Ichimoku, ATR-based, etc.)
- [ ] Parameter optimization (grid search)
- [ ] Walk-forward analysis
- [ ] Monte Carlo simulation
- [ ] Live trading integration
- [ ] Portfolio strategies (multiple assets simultaneously)
- [ ] Machine learning based strategies

## Support

For issues or questions, check:
- Review the code in `strategies_advanced.py` for strategy logic
- Check `config.py` for configuration options
- Examine `backtester.py` for backtest engine details

## License

MIT License - Use at your own risk

## Disclaimer

This software is for educational purposes only. Cryptocurrency trading carries significant risk. Never trade with money you can't afford to lose. Always do your own research and consider consulting with a financial advisor.
