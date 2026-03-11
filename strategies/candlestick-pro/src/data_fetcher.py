"""
Candlestick Pro - Data Fetcher

Fetches real OHLCV data from exchanges for multiple timeframes.
"""
from typing import List, Dict, Optional
import time
from datetime import datetime, timedelta
import ccxt
from src.models import Candle


class DataFetcher:
    """
    Fetches candlestick data from cryptocurrency exchanges.

    Supports:
    - Multiple timeframes simultaneously
    - Historical data retrieval
    - Real-time data updates
    """

    def __init__(self, exchange_id: str = "binance", testnet: bool = False):
        """
        Initialize data fetcher.

        Args:
            exchange_id: Exchange name (default: binance)
            testnet: Use testnet/sandbox if available
        """
        exchange_class = getattr(ccxt, exchange_id)

        if testnet and exchange_id == "binance":
            self.exchange = ccxt.binance({
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',
                },
            })
        else:
            self.exchange = exchange_class({'enableRateLimit': True})

        self.exchange.load_markets()

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
        since: Optional[int] = None
    ) -> List[Candle]:
        """
        Fetch OHLCV candles for a single timeframe.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Timeframe string ('1m', '5m', '15m', '1h', '4h', '1d')
            limit: Number of candles to fetch
            since: Timestamp in milliseconds for start time

        Returns:
            List of Candle objects
        """
        try:
            # Normalize symbol
            if symbol not in self.exchange.markets:
                # Try with slash
                symbol_with_slash = symbol.replace('/', '')
                if symbol_with_slash in self.exchange.markets:
                    symbol = self.exchange.markets[symbol_with_slash]['symbol']
                else:
                    raise ValueError(f"Symbol {symbol} not found on exchange")

            # Fetch OHLCV
            ohlcv = self.exchange.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                limit=limit,
                since=since
            )

            # Convert to Candle objects
            candles = []
            for candle_data in ohlcv:
                candles.append(Candle(
                    timestamp=candle_data[0],
                    open=float(candle_data[1]),
                    high=float(candle_data[2]),
                    low=float(candle_data[3]),
                    close=float(candle_data[4]),
                    volume=float(candle_data[5])
                ))

            return candles

        except Exception as e:
            print(f"Error fetching candles for {symbol} {timeframe}: {e}")
            return []

    def fetch_multiple_timeframes(
        self,
        symbol: str,
        timeframes: List[str],
        limit: int = 500
    ) -> Dict[str, List[Candle]]:
        """
        Fetch candles for multiple timeframes simultaneously.

        Args:
            symbol: Trading pair
            timeframes: List of timeframe strings
            limit: Candles per timeframe

        Returns:
            Dict mapping timeframe -> List[Candle]
        """
        result = {}

        for tf in timeframes:
            candles = self.fetch_candles(symbol, tf, limit)
            if candles:
                result[tf] = candles

            # Rate limiting
            time.sleep(0.1)

        return result

    def fetch_historical_range(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Candle]:
        """
        Fetch historical data for a date range.

        Note: Most exchanges have limits on historical data range.
        """
        all_candles = []
        current_time = int(start_date.timestamp() * 1000)
        end_time = int(end_date.timestamp() * 1000)

        # Fetch in batches
        while current_time < end_time:
            candles = self.fetch_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=1000,
                since=current_time
            )

            if not candles:
                break

            all_candles.extend(candles)
            current_time = candles[-1].timestamp + 1

            # Check if we've reached the end
            if candles[-1].timestamp >= end_time:
                break

            time.sleep(0.2)  # Rate limiting

        return all_candles

    def get_available_timeframes(self) -> List[str]:
        """Get list of available timeframes from exchange."""
        return list(self.exchange.timeframes.keys())

    def get_symbols(self, quote: str = "USDT") -> List[str]:
        """
        Get list of trading symbols filtered by quote currency.

        Args:
            quote: Quote currency (e.g., 'USDT', 'BTC')

        Returns:
            List of symbol strings
        """
        symbols = []
        for symbol, market in self.exchange.markets.items():
            if market['quote'] == quote and market['active']:
                symbols.append(symbol)
        return symbols

    def save_to_csv(self, candles: List[Candle], filepath: str):
        """Save candles to CSV file for backtesting."""
        import csv
        from pathlib import Path

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            for candle in candles:
                writer.writerow([
                    candle.timestamp,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume or 0
                ])

        print(f"Saved {len(candles)} candles to {filepath}")

    @staticmethod
    def load_from_csv(filepath: str) -> List[Candle]:
        """Load candles from CSV file."""
        import csv
        from pathlib import Path

        if not Path(filepath).exists():
            raise FileNotFoundError(f"CSV file not found: {filepath}")

        candles = []
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)

            for row in reader:
                candles.append(Candle(
                    timestamp=int(row['timestamp']),
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['volume']) if row['volume'] else None
                ))

        return candles
