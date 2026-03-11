#!/usr/bin/env python3
"""Test trailing stop strategy vs static stops."""
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
import json

# Load signals
print("Loading signals...")
signals = load_transactions_and_generate_signals(
    data_path="data/insider_transactions.json",
    source="secapi",
    threshold_usd=Decimal("100000"),
)

print(f"Generated {len(signals)} signals")

# Get price provider
price_provider = get_price_provider("yfinance")

# Test configurations
configs = [
    {
        "name": "Static Stops (8% SL, 16% TP)",
        "stop_loss_pct": Decimal("0.08"),
        "take_profit_pct": Decimal("0.16"),
        "trailing_stop_r": None,
    },
    {
        "name": "Trailing Stop (8% SL, 16% TP, 1R/2R trail)",
        "stop_loss_pct": Decimal("0.08"),
        "take_profit_pct": Decimal("0.16"),
        "trailing_stop_r": 2,  # Trail at 1R (breakeven) and 2R (lock 1R)
    },
    {
        "name": "Trailing Stop Only (8% SL, no TP, trail at 1R/2R)",
        "stop_loss_pct": Decimal("0.08"),
        "take_profit_pct": Decimal("1.00"),  # Effectively no TP
        "trailing_stop_r": 2,
    },
]

results = []

for config in configs:
    print(f"\n{'='*60}")
    print(f"Testing: {config['name']}")
    print(f"{'='*60}")

    engine = BacktestEngine(
        initial_cash=Decimal("100000"),
        stop_loss_pct=config["stop_loss_pct"],
        take_profit_pct=config["take_profit_pct"],
        price_provider=price_provider,
        trailing_stop_r=config["trailing_stop_r"],
        max_hold_bars=60,
    )

    result = engine.run(
        signals=signals,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    results.append({
        "config": config["name"],
        "total_return": float(result["summary"]["total_return"]) * 100,
        "cagr": float(result["summary"]["cagr"]) * 100,
        "max_dd": float(result["summary"]["max_drawdown"]) * 100,
        "sharpe": result["summary"]["sharpe_ratio"],
        "win_rate": float(result["trades"]["win_rate"]) * 100,
        "profit_factor": float(result["trades"]["profit_factor"]),
        "n_trades": result["trades"]["n_trades"],
    })

    # Print summary
    print(f"Total Return: {results[-1]['total_return']:.2f}%")
    print(f"CAGR: {results[-1]['cagr']:.2f}%")
    print(f"Max Drawdown: {results[-1]['max_dd']:.2f}%")
    print(f"Sharpe Ratio: {results[-1]['sharpe']:.2f}")
    print(f"Win Rate: {results[-1]['win_rate']:.1f}%")
    print(f"Profit Factor: {results[-1]['profit_factor']:.2f}")
    print(f"Trades: {results[-1]['n_trades']}")

# Print comparison table
print(f"\n{'='*80}")
print(f"COMPARISON TABLE")
print(f"{'='*80}")
print(f"{'Config':<50} {'Return':>10} {'CAGR':>8} {'DD':>8} {'Sharpe':>8} {'WR':>8} {'PF':>8}")
print(f"{'-'*80}")

for r in results:
    print(f"{r['config']:<50} {r['total_return']:>9.2f}% {r['cagr']:>8.2f}% {r['max_dd']:>8.2f}% {r['sharpe']:>8.2f} {r['win_rate']:>7.1f}% {r['profit_factor']:>8.2f}")

print(f"{'='*80}")
