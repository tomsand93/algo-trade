"""
pmirror CLI - Polymarket Copy-Trade Backtest System

Usage:
    pmirror fetch --wallet 0x... --start 2024-01-01 --end 2024-12-31
    pmirror backtest --wallet 0x... --policy mirror_latency --start 2024-01-01 --end 2024-12-31
    pmirror report --run-id <uuid>
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from pmirror.config import get_settings
from pmirror.data.data_api import DataAPIClient
from pmirror.data.storage import TradeStorage
from pmirror.domain.normalize import normalize_trades
from pmirror.backtest.runner import BacktestRunner
from pmirror.backtest.metrics import compute_metrics, format_metrics
from pmirror.reporting.report import generate_markdown_report, save_report as save_report_file
from pmirror.reporting.charts import (
    generate_equity_curve,
    generate_drawdown_chart,
    generate_returns_distribution,
)

app = typer.Typer(
    name="pmirror",
    help="Polymarket copy-trade backtest system",
    add_completion=False,
    no_args_is_help=True,
)


@app.command()
def fetch(
    wallet: str = typer.Option(
        ...,
        "--wallet",
        "-w",
        help="Wallet address to fetch data for (0x...)",
        metavar="ADDRESS",
    ),
    start: str = typer.Option(
        ...,
        "--start",
        "-s",
        help="Start date (YYYY-MM-DD)",
        metavar="DATE",
    ),
    end: str = typer.Option(
        ...,
        "--end",
        "-e",
        help="End date (YYYY-MM-DD)",
        metavar="DATE",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path for fetched data (default: data/clean/wallets/<wallet>.parquet)",
    ),
    limit: int = typer.Option(
        1000,
        "--limit",
        "-l",
        help="Maximum number of trades to fetch",
    ),
) -> None:
    """
    Fetch wallet trading data from Polymarket.

    Retrieves historical trades for the specified wallet and stores them
    in parquet format for backtesting.
    """
    settings = get_settings()

    # Parse dates
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as e:
        typer.echo(f"Error: Invalid date format. Use YYYY-MM-DD. {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Fetching data for wallet: {wallet}")
    typer.echo(f"Date range: {start} to {end}")
    typer.echo(f"Limit: {limit} trades")

    # Fetch trades from API
    try:
        client = DataAPIClient(settings)
        trades = client.get_wallet_trades(wallet, start_dt, end_dt, limit=limit)

        if not trades:
            typer.echo("No trades found for the specified wallet and date range.")
            raise typer.Exit(code=0)

        typer.echo(f"Fetched {len(trades)} trades")

    except Exception as e:
        typer.echo(f"Error fetching trades: {e}", err=True)
        raise typer.Exit(code=1)

    # Normalize and save
    try:
        storage = TradeStorage(settings)
        df = normalize_trades(trades)

        # Determine output path
        if output:
            output_path = Path(output)
        else:
            output_path = settings.data.clean_data_dir / "wallets" / f"{wallet.lower()}.parquet"

        # Save wallet-specific file
        saved_path = storage.save_wallet_trades(df, wallet)

        typer.echo(f"Saved {len(df)} trades to: {saved_path}")

        # Show trade summary
        if not df.empty:
            typer.echo(f"\nTrade summary:")
            typer.echo(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
            typer.echo(f"  Markets: {df['market_id'].nunique()}")
            typer.echo(f"  Buy orders: {len(df[df['side'] == 'buy'])}")
            typer.echo(f"  Sell orders: {len(df[df['side'] == 'sell'])}")

    except Exception as e:
        typer.echo(f"Error saving trades: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def backtest(
    wallet: str = typer.Option(
        ...,
        "--wallet",
        "-w",
        help="Wallet address to backtest",
        metavar="ADDRESS",
    ),
    policy: str = typer.Option(
        "mirror_latency",
        "--policy",
        "-p",
        help="Copy policy to use: mirror_latency, fixed_allocation, position_rebalance",
        metavar="POLICY",
    ),
    start: str = typer.Option(
        ...,
        "--start",
        "-s",
        help="Start date (YYYY-MM-DD)",
        metavar="DATE",
    ),
    end: str = typer.Option(
        ...,
        "--end",
        "-e",
        help="End date (YYYY-MM-DD)",
        metavar="DATE",
    ),
    capital: float = typer.Option(
        1000.0,
        "--capital",
        "-c",
        help="Starting capital for backtest (default: 1000)",
        metavar="AMOUNT",
    ),
    scale_factor: float = typer.Option(
        0.1,
        "--scale",
        help="Position scaling factor for mirror_latency (default: 0.1)",
    ),
    commission_rate: float = typer.Option(
        0.0,
        "--commission",
        help="Commission rate per trade (default: 0.0)",
    ),
    slippage_bps: int = typer.Option(
        5,
        "--slippage",
        help="Slippage in basis points (default: 5)",
    ),
    save_report: bool = typer.Option(
        False,
        "--save-report",
        "-r",
        help="Generate and save report after backtest",
    ),
) -> None:
    """
    Run a backtest using the specified copy policy.

    Simulates copying trades from the target wallet using the selected
    policy and calculates performance metrics.
    """
    settings = get_settings()

    # Parse dates
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as e:
        typer.echo(f"Error: Invalid date format. Use YYYY-MM-DD. {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Backtesting wallet: {wallet}")
    typer.echo(f"Policy: {policy}")
    typer.echo(f"Date range: {start} to {end}")
    typer.echo(f"Starting capital: ${capital:,.2f}")

    # Run backtest
    try:
        runner = BacktestRunner(storage=TradeStorage(settings))

        policy_params = {"scale_factor": scale_factor} if policy == "mirror_latency" else {}

        result = runner.run(
            target_wallet=wallet,
            start_date=start_dt,
            end_date=end_dt,
            capital=capital,
            policy=policy,
            policy_params=policy_params,
            commission_rate=commission_rate,
            slippage_bps=slippage_bps,
        )

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Error running backtest: {e}", err=True)
        raise typer.Exit(code=1)

    # Compute metrics
    metrics_dict = compute_metrics(result)

    # Display results
    typer.echo("\n" + format_metrics(metrics_dict))

    # Save report if requested
    if save_report:
        run_id = f"{wallet[:8]}_{start}_{end}"
        config = {
            "wallet": wallet,
            "policy": policy,
            "start": start,
            "end": end,
            "initial_cash": capital,
        }

        # Build BacktestMetrics-like object from dict
        from pmirror.domain.models import BacktestMetrics

        metrics_obj = BacktestMetrics(
            total_return=metrics_dict["total_return"],
            sharpe_ratio=metrics_dict["sharpe_ratio"],
            sortino_ratio=metrics_dict["sortino_ratio"],
            max_drawdown=metrics_dict["max_drawdown"],
            max_drawdown_duration=metrics_dict["max_drawdown_duration"],
            total_trades=metrics_dict["total_trades"],
            win_rate=metrics_dict["win_rate"],
            avg_trade_return=metrics_dict["avg_trade_return"],
            skipped_trades=metrics_dict["skipped_trades"],
            skipped_rate=metrics_dict["skip_rate"],
            max_exposure=metrics_dict["max_exposure"],
            avg_exposure=metrics_dict["avg_exposure"],
            final_equity=metrics_dict["final_equity"],
            peak_equity=metrics_dict["peak_equity"],
            total_fees=metrics_dict["total_fees"],
            target_return=0.0,  # Not computed yet
        )

        report = generate_markdown_report(metrics_obj, config, run_id=run_id)
        report_path = save_report_file(report, run_id, reports_dir=str(settings.reports_dir))

        typer.echo(f"\nReport saved to: {report_path}")

        # Generate charts if there are trades
        if result.executed_trades:
            charts_dir = Path(report_path).parent
            equity_curve = metrics_dict.get("equity_curve", [])

            if equity_curve:
                sorted_trades = sorted(result.executed_trades, key=lambda x: x.timestamp)
                # Equity curve includes initial capital, so add starting timestamp
                start_timestamp = sorted_trades[0].timestamp if sorted_trades else start_dt
                timestamps = [start_timestamp] + [t.timestamp for t in sorted_trades]

                # Generate equity curve chart
                equity_chart_path = charts_dir / "equity_curve.png"
                generate_equity_curve(
                    timestamps=timestamps,
                    cash_values=equity_curve,
                    output_path=str(equity_chart_path),
                    title=f"Equity Curve - {run_id}",
                )
                typer.echo(f"Equity chart saved to: {equity_chart_path}")

                # Generate drawdown chart
                dd_chart_path = charts_dir / "drawdown.png"
                generate_drawdown_chart(
                    timestamps=timestamps,
                    equity_values=equity_curve,
                    output_path=str(dd_chart_path),
                    title=f"Drawdown Analysis - {run_id}",
                )
                typer.echo(f"Drawdown chart saved to: {dd_chart_path}")

                # Save result JSON for report command
                result_file = charts_dir / "result.json"
                import json

                # Convert executed trades to dict for JSON serialization
                executed_trades_data = [
                    {
                        "timestamp": t.timestamp.isoformat(),
                        "market_id": t.market_id,
                        "side": t.side,
                        "price": t.price,
                        "size": t.size,
                        "fee": t.fee,
                    }
                    for t in result.executed_trades
                ]

                # Convert max_drawdown_duration to string for JSON
                metrics_for_json = metrics_dict.copy()
                metrics_for_json["max_drawdown_duration"] = str(metrics_for_json["max_drawdown_duration"])

                result_data = {
                    "metrics": metrics_for_json,
                    "config": config,
                    "executed_trades": executed_trades_data,
                    "equity_curve": equity_curve,
                }

                with open(result_file, "w") as f:
                    json.dump(result_data, f, indent=2, default=str)

                typer.echo(f"Result data saved to: {result_file}")


@app.command()
def report(
    run_id: str = typer.Argument(
        ...,
        help="Backtest run ID to generate report for",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path for report (default: reports/<run_id>/report.md)",
    ),
    charts: bool = typer.Option(
        True,
        "--charts/--no-charts",
        help="Generate chart images (default: True)",
    ),
) -> None:
    """
    Generate a report from a completed backtest run.

    Creates a detailed performance report with charts and metrics.
    The run_id should match a directory in the reports folder.
    """
    import json
    from pathlib import Path

    settings = get_settings()
    reports_dir = settings.data.reports_dir

    # Look for existing report data
    run_dir = Path(reports_dir) / run_id

    if not run_dir.exists():
        typer.echo(f"Error: No data found for run_id '{run_id}'", err=True)
        typer.echo(f"Expected directory: {run_dir}")
        typer.echo("\nAvailable runs:")
        if Path(reports_dir).exists():
            for d in Path(reports_dir).iterdir():
                if d.is_dir():
                    typer.echo(f"  - {d.name}")
        raise typer.Exit(code=1)

    # Check for existing report
    existing_report = run_dir / "report.md"
    if existing_report.exists():
        typer.echo(f"Report already exists at: {existing_report}")
        typer.echo(f"\nTo regenerate, delete the existing report first.")
        raise typer.Exit(code=0)

    # Try to load backtest result JSON
    result_file = run_dir / "result.json"
    if not result_file.exists():
        typer.echo(f"Error: No backtest result found at {result_file}", err=True)
        typer.echo("\nNote: Use --save-report when running backtest to save results.")
        raise typer.Exit(code=1)

    try:
        with open(result_file) as f:
            result_data = json.load(f)

        # Reconstruct BacktestMetrics from saved data
        from pmirror.domain.models import BacktestMetrics

        metrics = BacktestMetrics(**result_data["metrics"])
        config = result_data["config"]

        # Generate report
        report = generate_markdown_report(metrics, config, run_id=run_id)

        # Save report
        if output:
            report_path = Path(output)
            report_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            report_path = run_dir / "report.md"

        report_path.write_text(report)

        typer.echo(f"Report saved to: {report_path}")

        # Generate charts if requested
        if charts and result_data.get("executed_trades"):
            from datetime import datetime

            trades = result_data["executed_trades"]
            trade_timestamps = [datetime.fromisoformat(t["timestamp"]) for t in trades]
            equity_curve = result_data.get("equity_curve", [])

            if equity_curve and trade_timestamps:
                # Equity curve includes initial capital, add starting timestamp
                start_ts = trade_timestamps[0]
                timestamps = [start_ts] + trade_timestamps

                # Equity chart
                equity_chart_path = run_dir / "equity_curve.png"
                generate_equity_curve(
                    timestamps=timestamps,
                    cash_values=equity_curve,
                    output_path=str(equity_chart_path),
                    title=f"Equity Curve - {run_id}",
                )
                typer.echo(f"Equity chart: {equity_chart_path}")

                # Drawdown chart
                dd_chart_path = run_dir / "drawdown.png"
                generate_drawdown_chart(
                    timestamps=timestamps,
                    equity_values=equity_curve,
                    output_path=str(dd_chart_path),
                    title=f"Drawdown - {run_id}",
                )
                typer.echo(f"Drawdown chart: {dd_chart_path}")

    except Exception as e:
        typer.echo(f"Error generating report: {e}", err=True)
        raise typer.Exit(code=1)


def _version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        typer.echo("pmirror v0.1.0")
        raise typer.Exit()


@app.callback()
def cli(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """
    pmirror - Polymarket Copy-Trade Backtest System

    Backtest-first system to analyze Polymarket trader profitability
    by mirroring public wallet activity.
    """
    pass


if __name__ == "__main__":
    app()
