"""
End-of-day report generator.

Produces JSON + CSV snapshots and a human-readable summary.
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .tracker import MetricsTracker

log = logging.getLogger(__name__)


class DailyReporter:
    """Generates and saves end-of-day reports."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self, tracker: MetricsTracker, events: List[Dict]
    ) -> Dict:
        """Generate a complete end-of-day report."""
        combined = tracker.get_combined_metrics()
        date_str = datetime.now().strftime("%Y-%m-%d")

        report = {
            "date": date_str,
            "generated_at": datetime.now().isoformat(),
            "combined": combined,
            "accounts": {},
            "events_count": len(events),
        }

        for name, metrics in tracker.accounts.items():
            report["accounts"][name] = metrics.to_dict()

        return report

    def save_json(self, report: Dict) -> str:
        """Save report as JSON."""
        date_str = report["date"]
        path = self.data_dir / f"daily_report_{date_str}.json"
        path.write_text(json.dumps(report, indent=2, default=str))
        log.info("Daily report saved: %s", path)
        return str(path)

    def save_csv(self, report: Dict) -> str:
        """Save account summaries as CSV."""
        date_str = report["date"]
        path = self.data_dir / f"daily_summary_{date_str}.csv"

        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "date", "account", "equity", "cash",
                "daily_pnl", "daily_pnl_pct",
                "total_pnl", "total_pnl_pct",
                "unrealized_pnl", "realized_pnl",
                "trades_today", "win_rate",
                "max_drawdown_pct", "exposure",
                "position_count",
            ])

            for name, acct in report["accounts"].items():
                writer.writerow([
                    date_str, name,
                    f"{acct['equity']:.2f}",
                    f"{acct['cash']:.2f}",
                    f"{acct['daily_pnl']:.2f}",
                    f"{acct['daily_pnl_pct']:.2f}",
                    f"{acct['total_pnl']:.2f}",
                    f"{acct['total_pnl_pct']:.2f}",
                    f"{acct['unrealized_pnl']:.2f}",
                    f"{acct['realized_pnl']:.2f}",
                    acct["trades_today"],
                    f"{acct['win_rate']:.1f}",
                    f"{acct['max_drawdown_pct']:.2f}",
                    f"{acct['exposure']:.1f}",
                    acct["position_count"],
                ])

            # Combined row
            c = report["combined"]
            writer.writerow([
                date_str, "COMBINED",
                f"{c['total_equity']:.2f}", "",
                f"{c['total_daily_pnl']:.2f}",
                f"{c['total_daily_pnl_pct']:.2f}",
                f"{c['total_pnl']:.2f}",
                f"{c['total_pnl_pct']:.2f}",
                f"{c['total_unrealized']:.2f}",
                f"{c['total_realized']:.2f}",
                "", "", "", "",
                c["total_positions"],
            ])

        log.info("Daily CSV saved: %s", path)
        return str(path)

    def print_summary(self, report: Dict) -> str:
        """Generate a human-readable summary string."""
        c = report["combined"]
        lines = [
            "",
            "=" * 70,
            f"  END-OF-DAY REPORT — {report['date']}",
            "=" * 70,
            "",
            f"  Combined Equity:   ${c['total_equity']:>12,.2f}",
            f"  Combined Daily PnL: ${c['total_daily_pnl']:>11,.2f} ({c['total_daily_pnl_pct']:+.2f}%)",
            f"  Combined Total PnL: ${c['total_pnl']:>11,.2f} ({c['total_pnl_pct']:+.2f}%)",
            f"  Total Positions:    {c['total_positions']}",
            "",
            "  " + "-" * 66,
        ]

        for name, acct in report["accounts"].items():
            lines.extend([
                f"  [{name}]",
                f"    Equity:     ${acct['equity']:>10,.2f}  |  Daily PnL: ${acct['daily_pnl']:>8,.2f} ({acct['daily_pnl_pct']:+.2f}%)",
                f"    Total PnL:  ${acct['total_pnl']:>10,.2f}  |  Win Rate:  {acct['win_rate']:.1f}%",
                f"    Drawdown:   {acct['max_drawdown_pct']:.2f}%      |  Exposure:  {acct['exposure']:.1f}%",
                f"    Positions:  {acct['position_count']}            |  Trades:    {acct['trades_today']}",
                "  " + "-" * 66,
            ])

        lines.append("=" * 70)
        return "\n".join(lines)
