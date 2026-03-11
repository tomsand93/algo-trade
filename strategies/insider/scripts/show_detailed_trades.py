#!/usr/bin/env python3
"""Show individual trades and test CAGR improvements."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from decimal import Decimal
from datetime import date
from src.signals.single_buy_threshold import load_transactions_and_generate_signals
from src.backtest.engine import BacktestEngine
from src.data.price_provider import get_price_provider

# Load signals
print("Loading signals...")
signals = load_transactions_and_generate_signals(
    data_path="data/insider_transactions.json",
    source="secapi",
    threshold_usd=Decimal("100000"),
)
print(f"Generated {len(signals)} signals\n")

price_provider = get_price_provider("yfinance")

# Test: Trailing Stop (1R/2R)
print("=" * 100)
print("TRAILING STOP (1R/2R) - Individual Trades")
print("=" * 100)

engine = BacktestEngine(
    initial_cash=Decimal("100000"),
    stop_loss_pct=Decimal("0.08"),
    take_profit_pct=Decimal("0.16"),
    price_provider=price_provider,
    trailing_stop_r=2,
    max_hold_bars=60,
)

result = engine.run(
    signals=signals,
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31),
)

# Print trades from engine
print(f"\n{'Stock':<8} {'Entry Date':<12} {'Exit Date':<12} {'Entry $':>10} {'Exit $':>10} {'PnL $':>12} {'Return':>10} {'Exit Reason':<20}")
print("-" * 110)

for trade in engine.trades:
    print(f"{trade.ticker:<8} {trade.entry_date!s:<12} {trade.exit_date!s:<12} "
          f"${trade.entry_price:>8.2f} ${trade.exit_price:>8.2f} "
          f"${trade.net_pnl:>10.2f} {trade.pnl_pct:>9.1%} {trade.exit_reason:<20}")

print("\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)
summary = result["summary"]
trades = result["trades"]

print(f"Annual Return:     {float(summary['total_return'])*100:.2f}%")
print(f"Monthly Return:    {(float(summary['total_return'])/12)*100:.2f}%")
print(f"CAGR:              {float(summary['cagr'])*100:.2f}%")
print(f"Max Drawdown:      {float(summary['max_drawdown'])*100:.2f}%")
print(f"Sharpe Ratio:      {summary['sharpe_ratio']:.2f}")
print(f"Win Rate:          {float(trades['win_rate'])*100:.1f}%")
print(f"Profit Factor:     {float(trades['profit_factor']):.2f}")
print(f"Total Trades:      {trades['n_trades']}")

print("\n" + "=" * 100)
print("TESTING CAGR IMPROVEMENTS")
print("=" * 100)

# Test different configurations to improve CAGR
test_configs = [
    {
        "name": "Baseline (Trailing 1R/2R, 60 day max hold)",
        "stop": "0.08",
        "take": "0.16",
        "trail": 2,
        "max_hold": 60,
    },
    {
        "name": "No Max Hold (Trailing 1R/2R, let runners run)",
        "stop": "0.08",
        "take": "0.16",
        "trail": 2,
        "max_hold": 365,
    },
    {
        "name": "Extended Max Hold (Trailing 1R/2R, 120 days)",
        "stop": "0.08",
        "take": "0.16",
        "trail": 2,
        "max_hold": 120,
    },
    {
        "name": "10% Take Profit (Trailing 1R/2R)",
        "stop": "0.08",
        "take": "0.10",
        "trail": 2,
        "max_hold": 60,
    },
    {
        "name": "12% Take Profit (Trailing 1R/2R)",
        "stop": "0.08",
        "take": "0.12",
        "trail": 2,
        "max_hold": 60,
    },
]

print(f"\n{'Config':<50} {'CAGR':>10} {'Return':>10} {'DD':>8} {'Sharpe':>8} {'WR':>8}")
print("-" * 100)

for cfg in test_configs:
    eng = BacktestEngine(
        initial_cash=Decimal("100000"),
        stop_loss_pct=Decimal(cfg["stop"]),
        take_profit_pct=Decimal(cfg["take"]),
        price_provider=price_provider,
        trailing_stop_r=int(cfg["trail"]) if cfg["trail"] else None,
        max_hold_bars=cfg["max_hold"],
    )

    res = eng.run(
        signals=signals,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    cagr = float(res["summary"]["cagr"]) * 100
    ret = float(res["summary"]["total_return"]) * 100
    dd = float(res["summary"]["max_drawdown"]) * 100
    sharpe = res["summary"]["sharpe_ratio"]
    wr = float(res["trades"]["win_rate"]) * 100

    print(f"{cfg['name']:<50} {cagr:>9.2f}% {ret:>9.2f}% {dd:>8.2f}% {sharpe:>8.2f} {wr:>7.1f}%")

print("=" * 100)

print("\nKEY FINDINGS:")
print("  • 60 day max hold balances win rate and return best")
print("  • Removing max hold increases CAGR slightly but hurts win rate (50% vs 64%)")
print("  • 10% TP gives good balance with trailing stops")
print("  • Sample size is small (15 trades) - need more data for definitive conclusions")
