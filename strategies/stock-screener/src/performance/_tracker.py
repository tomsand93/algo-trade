"""Performance tracking for screener scores vs actual returns."""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import yfinance as yf

from ..screener.models import FilterResult
from ..providers.base import PriceData

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """
    Tracks screener predictions vs actual returns.

    Workflow:
    1. save_screening() - Save results with scores when screen runs
    2. update_returns() - Fetch actual returns after time passes
    3. analyze_performance() - Correlate scores with returns
    """

    def __init__(self, data_dir: str = "performance_data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.snapshots_file = self.data_dir / "snapshots.jsonl"

    def save_screening(
        self,
        results: list[FilterResult],
        price_data: dict[str, PriceData],
        config: dict
    ) -> str:
        """
        Save a screening snapshot for later performance analysis.

        Args:
            results: Filter results with scores
            price_data: Price data at screening time
            config: Config used for screening

        Returns:
            Path to saved snapshot
        """
        timestamp = datetime.now().isoformat()

        snapshot = {
            "timestamp": timestamp,
            "config": {
                "market_cap_threshold": self._get_criterion_value(config, "market_cap"),
                "pe_threshold": self._get_criterion_value(config, "pe_ratio"),
                "ma200_filter": self._has_criterion(config, "price_above_ma200"),
            },
            "stocks": []
        }

        for r in results:
            price = price_data.get(r.symbol)
            snapshot["stocks"].append({
                "symbol": r.symbol,
                "rank_score": r.rank_score,
                "value_score": r.scores.get("value_score"),
                "quality_score": r.scores.get("quality_score"),
                "momentum_score": r.scores.get("momentum_score"),
                "price_at_screen": price.price if price else None,
                "date_at_screen": timestamp
            })

        # Append to snapshots file
        with open(self.snapshots_file, "a") as f:
            f.write(json.dumps(snapshot) + "\n")

        logger.info(f"Saved screening snapshot with {len(results)} stocks")
        return str(self.snapshots_file)

    def update_returns(self, days_back: int = 30) -> pd.DataFrame:
        """
        Fetch actual returns for previous screenings.

        Args:
            days_back: How many days back to fetch returns for

        Returns:
            DataFrame with performance data
        """
        if not self.snapshots_file.exists():
            logger.warning("No snapshots found")
            return pd.DataFrame()

        records = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        with open(self.snapshots_file) as f:
            for line in f:
                snapshot = json.loads(line)
                screen_date = datetime.fromisoformat(snapshot["timestamp"])

                # Only update snapshots within range
                if screen_date < cutoff_date:
                    continue

                for stock in snapshot["stocks"]:
                    symbol = stock["symbol"]
                    price_then = stock.get("price_at_screen")

                    if not price_then:
                        continue

                    try:
                        # Fetch current price
                        ticker = yf.Ticker(symbol)
                        info = ticker.info
                        price_now = info.get("currentPrice") or info.get("regularMarketPrice")

                        if not price_now:
                            continue

                        # Calculate returns
                        return_pct = ((price_now - price_then) / price_then) * 100

                        records.append({
                            "symbol": symbol,
                            "screen_date": screen_date,
                            "price_then": price_then,
                            "price_now": price_now,
                            "return_pct": return_pct,
                            "rank_score": stock["rank_score"],
                            "value_score": stock.get("value_score"),
                            "quality_score": stock.get("quality_score"),
                            "momentum_score": stock.get("momentum_score"),
                            "days_held": (datetime.now() - screen_date).days
                        })

                    except Exception as e:
                        logger.warning(f"Error fetching returns for {symbol}: {e}")
                        continue

        df = pd.DataFrame(records)
        if not df.empty:
            logger.info(f"Updated returns for {len(df)} stocks")

            # Save updated results
            results_file = self.data_dir / f"performance_{datetime.now().strftime('%Y%m%d')}.csv"
            df.to_csv(results_file, index=False)
            logger.info(f"Saved performance data to {results_file}")

        return df

    def analyze_performance(self, df: Optional[pd.DataFrame] = None) -> dict:
        """
        Analyze correlation between scores and returns.

        Args:
            df: Performance data (if None, loads latest)

        Returns:
            Analysis results with correlations and metrics
        """
        if df is None:
            # Load latest performance file
            files = list(self.data_dir.glob("performance_*.csv"))
            if not files:
                return {"error": "No performance data found"}
            latest = max(files)
            df = pd.read_csv(latest)

        if df.empty:
            return {"error": "No data to analyze"}

        analysis = {
            "total_stocks": len(df),
            "avg_return": df["return_pct"].mean(),
            "median_return": df["return_pct"].median(),
            "std_return": df["return_pct"].std(),
            "win_rate": (df["return_pct"] > 0).sum() / len(df) * 100,
        }

        # Correlations
        for score_col in ["rank_score", "value_score", "quality_score", "momentum_score"]:
            if score_col in df.columns:
                corr = df[score_col].corr(df["return_pct"])
                analysis[f"{score_col}_correlation"] = corr

        # Quintile analysis
        df["quintile"] = pd.qcut(df["rank_score"], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"], duplicates="drop")

        quintile_returns = {}
        for q in ["Q1", "Q2", "Q3", "Q4", "Q5"]:
            if q in df["quintile"].values:
                quintile_returns[q] = df[df["quintile"] == q]["return_pct"].mean()

        analysis["quintile_returns"] = quintile_returns

        # Top vs Bottom performance
        if "Q1" in quintile_returns and "Q5" in quintile_returns:
            analysis["top_vs_bottom_spread"] = quintile_returns["Q5"] - quintile_returns["Q1"]

        return analysis

    def print_report(self, analysis: dict):
        """Print performance analysis report."""
        if "error" in analysis:
            print(f"Error: {analysis['error']}")
            return

        print("\n" + "="*60)
        print("SCREENING PERFORMANCE REPORT")
        print("="*60)

        print(f"\nTotal Stocks Tracked: {analysis['total_stocks']}")
        print(f"Average Return: {analysis['avg_return']:.2f}%")
        print(f"Median Return: {analysis['median_return']:.2f}%")
        print(f"Win Rate: {analysis['win_rate']:.1f}%")

        print("\n--- Score Correlations (higher = better predictive power) ---")
        for key, val in analysis.items():
            if "correlation" in key:
                score_name = key.replace("_correlation", "")
                print(f"  {score_name}: {val:.3f}")

        print("\n--- Quintile Returns (Q5 = highest score) ---")
        for q, ret in analysis.get("quintile_returns", {}).items():
            print(f"  {q}: {ret:.2f}%")

        if "top_vs_bottom_spread" in analysis:
            print(f"\nTop vs Bottom Spread: {analysis['top_vs_bottom_spread']:.2f}%")

        print("\n" + "="*60)

    def _get_criterion_value(self, config: dict, metric: str) -> Optional[float]:
        """Extract criterion value from config."""
        for c in config.get("criteria", []):
            if c.get("metric") == metric:
                return c.get("value")
        return None

    def _has_criterion(self, config: dict, metric: str) -> bool:
        """Check if config has a specific criterion."""
        for c in config.get("criteria", []):
            if c.get("metric") == metric:
                return True
        return False
