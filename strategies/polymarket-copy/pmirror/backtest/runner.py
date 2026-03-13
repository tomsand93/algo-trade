"""
High-level backtest runner with data loading and metrics.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from pmirror.domain import Trade
from pmirror.backtest.engine import BacktestEngine, BacktestConfig, BacktestResult
from pmirror.policies.base import CopyPolicy
from pmirror.policies.mirror_latency import MirrorLatencyPolicy
from pmirror.policies.fixed_allocation import FixedAllocationPolicy
from pmirror.policies.position_rebalance import PositionRebalancePolicy
from pmirror.data import TradeStorage


class BacktestRunner:
    """
    High-level interface for running backtests.

    Handles data loading, backtest execution, and result processing.
    """

    def __init__(
        self,
        storage: TradeStorage | None = None,
    ):
        """
        Initialize the backtest runner.

        Args:
            storage: TradeStorage instance for loading data
        """
        self.storage = storage or TradeStorage()

    def run(
        self,
        target_wallet: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        capital: float = 1000.0,
        policy: str | CopyPolicy = "mirror_latency",
        policy_params: dict | None = None,
        commission_rate: float = 0.0,
        slippage_bps: int = 5,
        trade_loader: Callable[[str, datetime, datetime], list[Trade]] | None = None,
    ) -> BacktestResult:
        """
        Run a backtest for the given target wallet.

        Args:
            target_wallet: Wallet address to follow
            start_date: Start date for backtest
            end_date: End date for backtest
            capital: Starting capital
            policy: Policy name or CopyPolicy instance
            policy_params: Additional parameters for policy
            commission_rate: Commission rate per trade
            slippage_bps: Slippage in basis points
            trade_loader: Optional function to load trades

        Returns:
            BacktestResult
        """
        # Load trades
        if trade_loader:
            trades = trade_loader(target_wallet, start_date or datetime.min, end_date or datetime.max)
        else:
            trades = self._load_wallet_trades(target_wallet, start_date, end_date)

        if not trades:
            return BacktestResult(
                final_state=self._empty_state(capital),
                config=BacktestConfig(
                    target_wallet=target_wallet,
                    capital=capital,
                    start_date=start_date,
                    end_date=end_date,
                ),
            )

        # Create policy
        if isinstance(policy, str):
            policy = self._create_policy(
                policy,
                capital,
                policy_params or {},
                commission_rate,
                slippage_bps,
            )

        # Create config
        config = BacktestConfig(
            target_wallet=target_wallet,
            capital=capital,
            start_date=start_date,
            end_date=end_date,
            policy=policy,
            commission_rate=commission_rate,
            slippage_bps=slippage_bps,
            trade_loader=trade_loader,
        )

        # Run backtest
        engine = BacktestEngine(config)
        result = engine.run(trades)

        # Compute basic metrics
        result.metrics = self._compute_metrics(result)

        return result

    def _load_wallet_trades(
        self,
        wallet: str,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> list[Trade]:
        """Load trades for a wallet from storage."""
        # Try to load from wallet-specific file
        df = self.storage.load_wallet_trades(wallet)

        if df.empty:
            # Try loading from main trades file and filter
            df = self.storage.load_trades()
            if not df.empty:
                df = df[df["maker"] == wallet.lower()]

        # Filter by date range
        if not df.empty:
            if start_date:
                df = df[df["timestamp"] >= pd.Timestamp(start_date)]
            if end_date:
                df = df[df["timestamp"] < pd.Timestamp(end_date)]

        # Convert to Trade objects
        trades = []
        for _, row in df.iterrows():
            trade = Trade(
                transaction_hash=row["transaction_hash"],
                timestamp=row["timestamp"],
                maker=row["maker"],
                taker=row.get("taker"),
                side=row["side"],
                outcome=row["outcome"],
                price=row["price"],
                size=row["size"],
                market_id=row["market_id"],
                shares=row.get("shares"),
                fee=row.get("fee"),
            )
            trades.append(trade)

        return trades

    def _create_policy(
        self,
        policy_name: str,
        capital: float,
        params: dict,
        commission_rate: float,
        slippage_bps: int,
    ) -> CopyPolicy:
        """Create a policy instance from name and parameters."""
        default_params = {
            "capital": capital,
            "commission_rate": commission_rate,
            "slippage_bps": slippage_bps,
        }
        default_params.update(params)

        policies = {
            "mirror_latency": MirrorLatencyPolicy,
            "fixed_allocation": FixedAllocationPolicy,
            "position_rebalance": PositionRebalancePolicy,
        }

        if policy_name not in policies:
            raise ValueError(f"Unknown policy: {policy_name}. Choose from {list(policies.keys())}")

        return policies[policy_name](**default_params)

    def _empty_state(self, capital: float):
        """Create an empty backtest state."""
        from pmirror.domain import BacktestState
        return BacktestState(cash=capital, starting_cash=capital)

    def _compute_metrics(self, result: BacktestResult) -> dict:
        """Compute basic performance metrics."""
        state = result.final_state

        return {
            "total_return": state.total_return,
            "final_equity": state.equity,
            "total_trades": len(result.executed_trades),
            "skipped_trades": len(result.skipped_trades),
            "skip_rate": result.skip_rate,
            "final_cash": state.cash,
            "num_positions": len(state.positions),
            "max_exposure": max([t.size for t in result.executed_trades], default=0),
        }


def run_backtest(
    target_wallet: str,
    trades: list[Trade] | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    capital: float = 1000.0,
    policy: str = "mirror_latency",
    scale_factor: float = 0.1,
    commission_rate: float = 0.0,
    slippage_bps: int = 5,
) -> BacktestResult:
    """
    Convenience function to run a backtest.

    Args:
        target_wallet: Wallet address to follow
        trades: Optional list of trades (if not provided, will load from storage)
        start_date: Start date for backtest
        end_date: End date for backtest
        capital: Starting capital
        policy: Policy name
        scale_factor: Position scaling factor (for mirror_latency)
        commission_rate: Commission rate per trade
        slippage_bps: Slippage in basis points

    Returns:
        BacktestResult
    """
    runner = BacktestRunner()

    policy_params = {"scale_factor": scale_factor} if policy == "mirror_latency" else {}

    if trades is not None:
        # Use provided trades
        from pmirror.backtest.engine import BacktestConfig, BacktestEngine
        from pmirror.policies.mirror_latency import MirrorLatencyPolicy

        config = BacktestConfig(
            target_wallet=target_wallet,
            capital=capital,
            start_date=start_date,
            end_date=end_date,
            policy=MirrorLatencyPolicy(
                capital=capital,
                scale_factor=scale_factor,
                commission_rate=commission_rate,
                slippage_bps=slippage_bps,
            ),
            commission_rate=commission_rate,
            slippage_bps=slippage_bps,
        )

        engine = BacktestEngine(config)
        result = engine.run(trades)
        result.metrics = runner._compute_metrics(result)
        return result
    else:
        # Load trades from storage
        return runner.run(
            target_wallet=target_wallet,
            start_date=start_date,
            end_date=end_date,
            capital=capital,
            policy=policy,
            policy_params=policy_params,
            commission_rate=commission_rate,
            slippage_bps=slippage_bps,
        )
