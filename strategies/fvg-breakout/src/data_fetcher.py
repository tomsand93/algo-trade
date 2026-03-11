"""Historical data loading for the FVG breakout strategy."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import pandas as pd
import requests


class AlpacaDataFetcher:
    """Fetch historical bar data from Alpaca Market Data API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: str = "https://data.alpaca.markets",
    ):
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self.api_secret = api_secret or os.environ.get("ALPACA_API_SECRET", "")
        self.base_url = base_url

        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Alpaca API credentials required. "
                "Set ALPACA_API_KEY and ALPACA_API_SECRET environment variables, "
                "or pass them directly."
            )

    def fetch_bars(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        adjustment: str = "raw",
    ) -> pd.DataFrame:
        """Fetch historical bars from Alpaca."""
        url = f"{self.base_url}/v2/stocks/{symbol}/bars"
        params = {
            "timeframe": timeframe,
            "start": f"{start_date}T09:30:00-05:00",
            "end": f"{end_date}T16:00:00-05:00",
            "adjustment": adjustment,
            "feed": "sip",
        }
        headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
        }

        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code != 200:
            raise Exception(f"Alpaca API error: {response.status_code} - {response.text}")

        data = response.json()
        if "bars" not in data or not data["bars"]:
            return pd.DataFrame()

        df = pd.DataFrame(data["bars"])
        df["t"] = pd.to_datetime(df["t"])
        df = df.set_index("t")
        df.index = df.index.tz_convert("America/New_York")
        df = df.rename(
            columns={
                "o": "open",
                "h": "high",
                "l": "low",
                "c": "close",
                "v": "volume",
                "vw": "vwap",
                "n": "trade_count",
            }
        )
        df = df.between_time("09:30", "16:00")
        return df[["open", "high", "low", "close", "volume"]]

    def fetch_multi_timeframe(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        timeframes: List[str] = ["5Min", "1Min"],
    ) -> Dict[str, Dict[str, pd.DataFrame]]:
        """Fetch multiple symbols and timeframes."""
        result: Dict[str, Dict[str, pd.DataFrame]] = {}
        for symbol in symbols:
            result[symbol] = {}
            for timeframe in timeframes:
                print(f"Fetching {timeframe} data for {symbol}...")
                try:
                    result[symbol][timeframe] = self.fetch_bars(
                        symbol=symbol,
                        timeframe=timeframe,
                        start_date=start_date,
                        end_date=end_date,
                    )
                except Exception as exc:
                    print(f"Error fetching {symbol} {timeframe}: {exc}")
                    result[symbol][timeframe] = pd.DataFrame()
        return result

    def save_data(self, data: Dict[str, Dict[str, pd.DataFrame]], output_dir: str) -> None:
        """Save fetched data to parquet files."""
        os.makedirs(output_dir, exist_ok=True)
        for symbol, timeframe_data in data.items():
            for timeframe, df in timeframe_data.items():
                if df.empty:
                    continue
                filepath = os.path.join(output_dir, f"{symbol}_{timeframe}.parquet")
                df.to_parquet(filepath)
                print(f"Saved {filepath}")

    def load_data(
        self,
        symbols: List[str],
        timeframes: List[str],
        data_dir: str,
    ) -> Dict[str, Dict[str, pd.DataFrame]]:
        """Load cached parquet data from disk."""
        result: Dict[str, Dict[str, pd.DataFrame]] = {}
        for symbol in symbols:
            result[symbol] = {}
            for timeframe in timeframes:
                filepath = os.path.join(data_dir, f"{symbol}_{timeframe}.parquet")
                if os.path.exists(filepath):
                    result[symbol][timeframe] = pd.read_parquet(filepath)
                    print(f"Loaded {filepath}")
                else:
                    result[symbol][timeframe] = pd.DataFrame()
                    print(f"File not found: {filepath}")
        return result


class CSVDataLoader:
    """Load data from local CSV files."""

    @staticmethod
    def load_csv(filepath: str, symbol: str, timeframe: str) -> pd.DataFrame:
        """Load a single CSV file."""
        df = pd.read_csv(filepath)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")

        if df.index.tz is None:
            df.index = df.index.tz_localize("America/New_York")

        df = df.between_time("09:30", "16:00")
        return df[["open", "high", "low", "close", "volume"]]

    @staticmethod
    def load_directory(
        data_dir: str,
        symbols: List[str],
        timeframes: List[str],
    ) -> Dict[str, Dict[str, pd.DataFrame]]:
        """Load all expected CSV files from a directory."""
        result: Dict[str, Dict[str, pd.DataFrame]] = {}
        for symbol in symbols:
            result[symbol] = {}
            for timeframe in timeframes:
                filename = f"{symbol}_{timeframe}.csv"
                filepath = os.path.join(data_dir, filename)
                try:
                    result[symbol][timeframe] = CSVDataLoader.load_csv(
                        filepath=filepath,
                        symbol=symbol,
                        timeframe=timeframe,
                    )
                except FileNotFoundError:
                    print(f"File not found: {filepath}")
                    result[symbol][timeframe] = pd.DataFrame()
        return result


def _print_validation_issues(
    data: Dict[str, Dict[str, pd.DataFrame]],
    symbols: List[str],
    timeframes: List[str],
    start_date: str,
    end_date: str,
) -> bool:
    """Validate dataframes and print any issues."""
    all_valid = True
    for symbol in symbols:
        for timeframe in timeframes:
            df = data[symbol][timeframe]
            validation = validate_data_coverage(df, symbol, timeframe, start_date, end_date)
            if validation["valid"]:
                continue
            all_valid = False
            print(f"Warning: {symbol} {timeframe} -")
            for issue in validation["issues"]:
                print(f"     {issue}")
    return all_valid


def get_data(
    symbols: List[str],
    start_date: str,
    end_date: str,
    use_cache: bool = True,
    cache_dir: str = "./data",
    use_csv: bool = False,
    csv_dir: str = "./csv_data",
    validate: bool = True,
) -> Dict[str, Dict[str, pd.DataFrame]]:
    """Get strategy data from CSV, cache, or Alpaca."""
    timeframes = ["5Min", "1Min"]

    if use_csv:
        data = CSVDataLoader.load_directory(csv_dir, symbols, timeframes)
        if validate:
            print("Validating CSV data...")
            _print_validation_issues(data, symbols, timeframes, start_date, end_date)
        return data

    fetcher = AlpacaDataFetcher()

    if use_cache:
        cached = fetcher.load_data(symbols, timeframes, cache_dir)
        if not validate or _print_validation_issues(
            cached, symbols, timeframes, start_date, end_date
        ):
            print("Using cached data (validated).")
            return cached

    print("Fetching fresh data from Alpaca...")
    data = fetcher.fetch_multi_timeframe(symbols, start_date, end_date, timeframes)

    if validate:
        print("Validating fetched data...")
        _print_validation_issues(data, symbols, timeframes, start_date, end_date)

    fetcher.save_data(data, cache_dir)
    return data


def validate_data_coverage(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
) -> dict:
    """Validate basic schema and requested date coverage."""
    issues = []

    if df.empty:
        issues.append(f"{symbol} {timeframe}: DataFrame is empty")
        return {"valid": False, "issues": issues}

    required_columns = {"open", "high", "low", "close", "volume"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        issues.append(
            f"{symbol} {timeframe}: Missing columns: {', '.join(sorted(missing_columns))}"
        )

    data_start = df.index.min()
    data_end = df.index.max()

    if data_start.tz:
        req_start = pd.Timestamp(start_date).tz_localize(data_start.tz)
    else:
        req_start = pd.Timestamp(start_date)

    if data_end.tz:
        req_end = pd.Timestamp(end_date).tz_localize(data_end.tz)
    else:
        req_end = pd.Timestamp(end_date)

    if data_start.normalize() > req_start.normalize():
        issues.append(
            f"{symbol} {timeframe}: Data starts {data_start.strftime('%Y-%m-%d')}, "
            f"but requested start is {start_date}"
        )

    if data_end.normalize() < req_end.normalize():
        issues.append(
            f"{symbol} {timeframe}: Data ends {data_end.strftime('%Y-%m-%d')}, "
            f"but requested end is {end_date}"
        )

    market_hours_data = df.between_time("09:30", "16:00")
    if market_hours_data.empty:
        issues.append(f"{symbol} {timeframe}: No data found during market hours (09:30-16:00 ET)")

    return {"valid": len(issues) == 0, "issues": issues}
