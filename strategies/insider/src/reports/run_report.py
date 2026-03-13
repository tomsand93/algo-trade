"""
Generate comprehensive backtest report.

Creates:
- Text summary with key metrics
- JSON dump of full results
- Plots (equity curve, drawdown, trade distribution)
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from .plots import create_full_report

logger = logging.getLogger(__name__)


def generate_report(
    backtest_results: Dict[str, Any],
    trades: List[Any],
    output_dir: str,
    benchmark_ticker: Optional[str] = None,
) -> None:
    """
    Generate comprehensive backtest report.

    Args:
        backtest_results: Results from BacktestEngine.run()
        trades: List of TradeResult objects
        output_dir: Directory to save report
        benchmark_ticker: Optional benchmark ticker for comparison
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Save full JSON results
    json_path = output_path / "results.json"

    # Convert trade results to dicts for JSON serialization
    trades_dict = [
        {
            "ticker": t.ticker,
            "entry_date": t.entry_date.isoformat(),
            "exit_date": t.exit_date.isoformat(),
            "entry_price": str(t.entry_price),
            "exit_price": str(t.exit_price),
            "shares": str(t.shares),
            "gross_pnl": str(t.gross_pnl),
            "costs": str(t.costs),
            "net_pnl": str(t.net_pnl),
            "pnl_pct": str(t.pnl_pct),
            "hold_bars": t.hold_bars,
            "exit_reason": t.exit_reason,
        }
        for t in trades
    ]

    report_data = {
        "backtest_results": backtest_results,
        "trades": trades_dict,
    }

    with open(json_path, "w") as f:
        json.dump(report_data, f, indent=2)

    logger.info(f"Full results saved to {json_path}")

    # Generate text summary
    summary_path = output_path / "summary.txt"
    _generate_text_summary(backtest_results, trades, summary_path)

    # Generate plots
    create_full_report(backtest_results, trades_dict, str(output_path / "plots"))

    logger.info(f"Report generated in {output_dir}")


def _generate_text_summary(
    results: Dict[str, Any],
    trades: List[Any],
    output_path: Path,
) -> None:
    """Generate text summary of results."""
    summary = results["summary"]
    trade_metrics = results["trades"]

    lines = [
        "=" * 60,
        "INSIDER BUY STRATEGY - BACKTEST RESULTS",
        "=" * 60,
        "",
        "PERIOD",
        "-" * 40,
        f"Start Date:    {summary['start_date']}",
        f"End Date:      {summary['end_date']}",
        "",
        "RETURN METRICS",
        "-" * 40,
        f"Total Return: {float(summary['total_return'])*100:.2f}%",
        f"CAGR:         {float(summary['cagr'])*100:.2f}%",
        f"Max Drawdown: {float(summary['max_drawdown'])*100:.2f}%",
        f"Sharpe Ratio: {summary['sharpe_ratio']:.2f}",
        "",
        "TRADING STATISTICS",
        "-" * 40,
        f"Total Trades:    {trade_metrics['n_trades']}",
        f"Win Rate:        {float(trade_metrics['win_rate'])*100:.1f}%",
        f"Avg Win:         ${float(trade_metrics['avg_win']):.2f}",
        f"Avg Loss:        ${float(trade_metrics['avg_loss']):.2f}",
        f"Profit Factor:   {float(trade_metrics['profit_factor']):.2f}",
        f"Avg Hold Bars:   {float(trade_metrics['avg_hold_bars']):.1f}",
        "",
        "PORTFOLIO METRICS",
        "-" * 40,
        f"Exposure:        {float(results['portfolio']['exposure'])*100:.1f}%",
        f"Avg Positions:   {results['portfolio']['avg_positions']:.1f}",
        "",
        "=" * 60,
    ]

    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    logger.info(f"Text summary saved to {output_path}")


def print_summary(results: Dict[str, Any]) -> None:
    """Print summary to console."""
    summary = results["summary"]
    trade_metrics = results["trades"]

    print("\n" + "=" * 50)
    print("BACKTEST SUMMARY")
    print("=" * 50)
    print(f"Period: {summary['start_date']} to {summary['end_date']}")
    print("\nReturns:")
    print(f"  Total: {float(summary['total_return'])*100:.2f}%")
    print(f"  CAGR:  {float(summary['cagr'])*100:.2f}%")
    print(f"  DD:    {float(summary['max_drawdown'])*100:.2f}%")
    print(f"  Sharpe: {summary['sharpe_ratio']:.2f}")
    print("\nTrading:")
    print(f"  Trades: {trade_metrics['n_trades']}")
    print(f"  Win Rate: {float(trade_metrics['win_rate'])*100:.1f}%")
    print(f"  Profit Factor: {float(trade_metrics['profit_factor']):.2f}")
    print("=" * 50 + "\n")
