"""
Backtesting Engine

Simulates trading with realistic commission, slippage, and position sizing
Calculates comprehensive performance metrics
"""
import pandas as pd
import numpy as np
from typing import Callable, Dict
import config


class BacktestEngine:
    """
    Backtesting engine for trading strategies
    """

    def __init__(self, initial_capital=None, commission=None, slippage=None):
        """
        Initialize backtest engine

        Args:
            initial_capital: Starting capital (default: from config)
            commission: Trading fee as decimal (default: from config)
            slippage: Price slippage as decimal (default: from config)
        """
        self.initial_capital = initial_capital or config.INITIAL_CAPITAL
        self.commission = commission or config.COMMISSION
        self.slippage = slippage or config.SLIPPAGE

    def run(self, df: pd.DataFrame, strategy_func: Callable, risk_per_trade: float = 0.10) -> Dict:
        """
        Run backtest on historical data

        Args:
            df: DataFrame with OHLCV data
            strategy_func: Strategy function returning 1 (buy), -1 (sell), or 0 (hold)
            risk_per_trade: Fraction of capital to risk per trade

        Returns:
            Dictionary with results and metrics
        """
        if df.empty or len(df) < 50:
            return self._empty_results()

        # Initialize tracking
        capital = self.initial_capital
        position = 0  # Quantity held
        entry_price = 0
        trades = []
        equity_curve = []

        # Simulate trading
        for i in range(len(df)):
            current_data = df.iloc[:i+1]
            current_price = float(df.iloc[i]['close'])

            # Calculate equity
            if position > 0:
                equity = capital + (position * current_price)
            else:
                equity = capital

            equity_curve.append({
                'timestamp': df.index[i],
                'equity': equity,
                'price': current_price
            })

            # Get strategy signal
            signal = strategy_func(current_data)

            # Execute BUY
            if signal == 1 and position == 0:
                trade_amount = capital * risk_per_trade
                exec_price = current_price * (1 + self.slippage)
                commission_cost = trade_amount * self.commission

                if trade_amount <= capital:
                    position = (trade_amount - commission_cost) / exec_price
                    entry_price = exec_price
                    capital -= trade_amount

                    trades.append({
                        'timestamp': df.index[i],
                        'type': 'BUY',
                        'price': exec_price,
                        'quantity': position,
                        'value': trade_amount,
                        'commission': commission_cost
                    })

            # Execute SELL
            elif signal == -1 and position > 0:
                exec_price = current_price * (1 - self.slippage)
                gross_proceeds = position * exec_price
                commission_cost = gross_proceeds * self.commission
                net_proceeds = gross_proceeds - commission_cost

                # Calculate P&L
                pnl = net_proceeds - (position * entry_price)
                pnl_pct = (exec_price - entry_price) / entry_price

                capital += net_proceeds

                trades.append({
                    'timestamp': df.index[i],
                    'type': 'SELL',
                    'price': exec_price,
                    'quantity': position,
                    'value': gross_proceeds,
                    'commission': commission_cost,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct
                })

                position = 0
                entry_price = 0

        # Close any open position
        if position > 0:
            final_price = float(df.iloc[-1]['close'])
            exec_price = final_price * (1 - self.slippage)
            gross_proceeds = position * exec_price
            commission_cost = gross_proceeds * self.commission
            net_proceeds = gross_proceeds - commission_cost
            pnl = net_proceeds - (position * entry_price)
            pnl_pct = (exec_price - entry_price) / entry_price

            capital += net_proceeds

            trades.append({
                'timestamp': df.index[-1],
                'type': 'SELL',
                'price': exec_price,
                'quantity': position,
                'value': gross_proceeds,
                'commission': commission_cost,
                'pnl': pnl,
                'pnl_pct': pnl_pct
            })

        # Calculate metrics
        final_equity = capital
        metrics = self._calculate_metrics(equity_curve, trades, self.initial_capital, final_equity)

        return {
            'final_equity': final_equity,
            'metrics': metrics,
            'trades': trades,
            'equity_curve': equity_curve
        }

    def _calculate_metrics(self, equity_curve, trades, initial_capital, final_equity):
        """Calculate comprehensive performance metrics"""

        # Basic metrics
        total_return = final_equity - initial_capital
        total_return_pct = (final_equity / initial_capital - 1) * 100

        # Trade analysis
        sell_trades = [t for t in trades if t['type'] == 'SELL' and 'pnl' in t]
        num_trades = len(sell_trades)

        if num_trades == 0:
            return self._empty_metrics(total_return, total_return_pct)

        # Win/Loss analysis
        winning_trades = [t for t in sell_trades if t['pnl'] > 0]
        losing_trades = [t for t in sell_trades if t['pnl'] <= 0]

        win_rate = (len(winning_trades) / num_trades * 100) if num_trades > 0 else 0

        avg_win = np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([abs(t['pnl']) for t in losing_trades]) if losing_trades else 0

        total_wins = sum([t['pnl'] for t in winning_trades])
        total_losses = abs(sum([t['pnl'] for t in losing_trades]))

        profit_factor = (total_wins / total_losses) if total_losses > 0 else (total_wins if total_wins > 0 else 0)

        # Drawdown calculation
        equity_values = [e['equity'] for e in equity_curve]
        running_max = np.maximum.accumulate(equity_values)
        drawdowns = (equity_values - running_max) / running_max * 100
        max_drawdown_pct = abs(np.min(drawdowns))
        max_drawdown = abs(np.min(equity_values - running_max))

        # Risk metrics
        equity_series = pd.Series(equity_values)
        returns = equity_series.pct_change().dropna()

        if len(returns) > 1 and returns.std() > 0:
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252)
        else:
            sharpe_ratio = 0

        # Sortino ratio (downside deviation only)
        negative_returns = returns[returns < 0]
        if len(negative_returns) > 1 and negative_returns.std() > 0:
            sortino_ratio = (returns.mean() / negative_returns.std()) * np.sqrt(252)
        else:
            sortino_ratio = 0

        # Additional metrics
        total_commission = sum([t.get('commission', 0) for t in trades])

        best_trade = max([t['pnl'] for t in sell_trades]) if sell_trades else 0
        worst_trade = min([t['pnl'] for t in sell_trades]) if sell_trades else 0

        avg_trade_duration = self._calculate_avg_trade_duration(trades)

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
            'total_commission': total_commission,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'avg_trade_duration_hours': avg_trade_duration,
            'num_winning_trades': len(winning_trades),
            'num_losing_trades': len(losing_trades),
        }

    def _calculate_avg_trade_duration(self, trades):
        """Calculate average trade duration in hours"""
        buy_trades = [t for t in trades if t['type'] == 'BUY']
        sell_trades = [t for t in trades if t['type'] == 'SELL']

        if not buy_trades or not sell_trades:
            return 0

        durations = []
        for i in range(min(len(buy_trades), len(sell_trades))):
            duration = (sell_trades[i]['timestamp'] - buy_trades[i]['timestamp']).total_seconds() / 3600
            durations.append(duration)

        return np.mean(durations) if durations else 0

    def _empty_metrics(self, total_return=0, total_return_pct=0):
        """Return empty metrics"""
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
            'total_commission': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'avg_trade_duration_hours': 0,
            'num_winning_trades': 0,
            'num_losing_trades': 0,
        }

    def _empty_results(self):
        """Return empty results for invalid data"""
        return {
            'final_equity': self.initial_capital,
            'metrics': self._empty_metrics(),
            'trades': [],
            'equity_curve': []
        }
