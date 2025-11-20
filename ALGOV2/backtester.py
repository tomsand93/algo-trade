"""
Backtesting Engine with Performance Metrics

Supports:
- Multiple position sizing strategies
- Commission/fee calculation
- Slippage simulation
- Performance metrics (Sharpe, Sortino, Max Drawdown, Win Rate, etc.)
"""
import pandas as pd
import numpy as np
from typing import Dict, Callable


class Backtester:
    """
    Backtesting engine for trading strategies
    """

    def __init__(
        self,
        initial_capital=10000,
        commission=0.001,  # 0.1% per trade (Binance standard)
        slippage=0.0005,   # 0.05% slippage
    ):
        """
        Initialize backtester

        Args:
            initial_capital: Starting capital in USD
            commission: Trading fee as decimal (0.001 = 0.1%)
            slippage: Price slippage as decimal (0.0005 = 0.05%)
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

    def run(
        self,
        df: pd.DataFrame,
        strategy_func: Callable,
        risk_per_trade: float = 0.10
    ) -> Dict:
        """
        Run backtest on historical data

        Args:
            df: DataFrame with OHLCV data
            strategy_func: Strategy function that returns 1 (buy), -1 (sell), or 0 (hold)
            risk_per_trade: Fraction of capital to risk per trade (0.10 = 10%)

        Returns:
            Dictionary with backtest results and metrics
        """
        if df.empty or len(df) < 50:
            return self._empty_results()

        # Initialize tracking variables
        capital = self.initial_capital
        position = 0  # Number of coins held
        position_value = 0  # Value of position in USD
        entry_price = 0
        trades = []
        equity_curve = []

        # Track for each candle
        for i in range(len(df)):
            current_slice = df.iloc[:i+1]

            # Get current price
            current_price = float(df.iloc[i]['close'])

            # Calculate current equity
            if position > 0:
                position_value = position * current_price
                current_equity = capital + position_value
            else:
                current_equity = capital

            equity_curve.append({
                'timestamp': df.index[i],
                'equity': current_equity,
                'price': current_price
            })

            # Get signal from strategy
            signal = strategy_func(current_slice)

            # Execute trades based on signal
            if signal == 1 and position == 0:  # BUY SIGNAL
                # Calculate position size
                trade_amount = capital * risk_per_trade

                # Apply slippage (buy at slightly higher price)
                execution_price = current_price * (1 + self.slippage)

                # Calculate commission
                gross_position = trade_amount / execution_price
                commission_amount = trade_amount * self.commission

                # Net position after commission
                net_position = (trade_amount - commission_amount) / execution_price

                if trade_amount <= capital:
                    position = net_position
                    entry_price = execution_price
                    capital -= trade_amount

                    trades.append({
                        'timestamp': df.index[i],
                        'type': 'BUY',
                        'price': execution_price,
                        'quantity': net_position,
                        'value': trade_amount,
                        'commission': commission_amount
                    })

            elif signal == -1 and position > 0:  # SELL SIGNAL
                # Apply slippage (sell at slightly lower price)
                execution_price = current_price * (1 - self.slippage)

                # Calculate sale proceeds
                gross_proceeds = position * execution_price
                commission_amount = gross_proceeds * self.commission
                net_proceeds = gross_proceeds - commission_amount

                # Calculate P&L
                pnl = net_proceeds - (position * entry_price)
                pnl_pct = (execution_price - entry_price) / entry_price

                capital += net_proceeds

                trades.append({
                    'timestamp': df.index[i],
                    'type': 'SELL',
                    'price': execution_price,
                    'quantity': position,
                    'value': gross_proceeds,
                    'commission': commission_amount,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct
                })

                position = 0
                entry_price = 0

        # Close any open position at the end
        if position > 0:
            final_price = float(df.iloc[-1]['close'])
            execution_price = final_price * (1 - self.slippage)
            gross_proceeds = position * execution_price
            commission_amount = gross_proceeds * self.commission
            net_proceeds = gross_proceeds - commission_amount
            pnl = net_proceeds - (position * entry_price)
            pnl_pct = (execution_price - entry_price) / entry_price

            capital += net_proceeds

            trades.append({
                'timestamp': df.index[-1],
                'type': 'SELL',
                'price': execution_price,
                'quantity': position,
                'value': gross_proceeds,
                'commission': commission_amount,
                'pnl': pnl,
                'pnl_pct': pnl_pct
            })

        # Calculate metrics
        final_equity = capital
        metrics = self._calculate_metrics(
            equity_curve,
            trades,
            self.initial_capital,
            final_equity
        )

        return {
            'final_equity': final_equity,
            'metrics': metrics,
            'trades': trades,
            'equity_curve': equity_curve
        }

    def _calculate_metrics(self, equity_curve, trades, initial_capital, final_equity):
        """Calculate performance metrics"""

        # Basic metrics
        total_return = final_equity - initial_capital
        total_return_pct = (final_equity / initial_capital - 1) * 100

        # Trade analysis
        num_trades = len([t for t in trades if t['type'] == 'SELL'])

        if num_trades == 0:
            return {
                'total_return': total_return,
                'total_return_pct': total_return_pct,
                'num_trades': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'max_drawdown': 0,
                'max_drawdown_pct': 0,
                'sharpe_ratio': 0,
                'sortino_ratio': 0,
            }

        # Winning/Losing trades
        sell_trades = [t for t in trades if t['type'] == 'SELL' and 'pnl' in t]
        winning_trades = [t for t in sell_trades if t['pnl'] > 0]
        losing_trades = [t for t in sell_trades if t['pnl'] <= 0]

        win_rate = len(winning_trades) / len(sell_trades) * 100 if sell_trades else 0

        avg_win = np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([abs(t['pnl']) for t in losing_trades]) if losing_trades else 0

        total_wins = sum([t['pnl'] for t in winning_trades]) if winning_trades else 0
        total_losses = abs(sum([t['pnl'] for t in losing_trades])) if losing_trades else 0

        profit_factor = total_wins / total_losses if total_losses > 0 else (total_wins if total_wins > 0 else 0)

        # Drawdown calculation
        equity_values = [e['equity'] for e in equity_curve]
        running_max = np.maximum.accumulate(equity_values)
        drawdowns = (equity_values - running_max) / running_max * 100
        max_drawdown_pct = abs(np.min(drawdowns))
        max_drawdown = abs(np.min(equity_values - running_max))

        # Returns for Sharpe/Sortino
        equity_series = pd.Series(equity_values)
        returns = equity_series.pct_change().dropna()

        if len(returns) > 0 and returns.std() > 0:
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252)  # Annualized
        else:
            sharpe_ratio = 0

        # Sortino ratio (uses only downside deviation)
        negative_returns = returns[returns < 0]
        if len(negative_returns) > 0 and negative_returns.std() > 0:
            sortino_ratio = (returns.mean() / negative_returns.std()) * np.sqrt(252)
        else:
            sortino_ratio = 0

        return {
            'total_return': total_return,
            'total_return_pct': total_return_pct,
            'num_trades': num_trades,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'total_commission': sum([t.get('commission', 0) for t in trades])
        }

    def _empty_results(self):
        """Return empty results for invalid data"""
        return {
            'final_equity': self.initial_capital,
            'metrics': {
                'total_return': 0,
                'total_return_pct': 0,
                'num_trades': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'max_drawdown': 0,
                'max_drawdown_pct': 0,
                'sharpe_ratio': 0,
                'sortino_ratio': 0,
                'total_commission': 0
            },
            'trades': [],
            'equity_curve': []
        }
