"""Output formatting for screener results."""

import json
import csv
from pathlib import Path
from typing import Optional
from datetime import datetime

from ..screener.models import FilterResult
from ..providers.base import PriceData, FundamentalData, NewsHeadline


class OutputFormatter:
    """Formats and saves screener results."""

    def __init__(self, output_dir: str = "results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def save_markdown(
        self,
        results: list[FilterResult],
        price_data: dict[str, PriceData],
        fund_data: dict[str, FundamentalData],
        news_data: Optional[dict[str, list[NewsHeadline]]] = None
    ) -> str:
        """Generate markdown report."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"# Stock Screener Results",
            f"**Generated:** {timestamp}",
            f"**Passing Stocks:** {len(results)}",
            "",
            "## Top Picks",
            ""
        ]

        # Create table
        if results:
            headers = ["Symbol", "Price", "P/E", "Div Yield", "Value", "Quality", "Momentum", "Rank"]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|" + "|".join(["---"] * len(headers)) + "|")

            for r in results[:20]:  # Top 20 in table
                price = price_data.get(r.symbol)
                fund = fund_data.get(r.symbol)

                lines.append("| " + " | ".join([
                    r.symbol,
                    f"${price.price:.2f}" if price else "N/A",
                    f"{fund.pe_ratio:.1f}" if fund and fund.pe_ratio else "N/A",
                    f"{fund.dividend_yield*100:.1f}%" if fund and fund.dividend_yield else "N/A",
                    f"{r.scores.get('value_score', 0):.0f}",
                    f"{r.scores.get('quality_score', 0):.0f}",
                    f"{r.scores.get('momentum_score', 0):.0f}",
                    f"{r.rank_score:.2f}"
                ]) + " |")

        # Analysis section
        lines.extend([
            "",
            "## Analysis",
            "",
            self._generate_analysis(results),
            "",
            "## Risks & Caveats",
            "",
            "- Data freshness varies by provider",
            "- Missing fundamental data may exclude valid stocks",
            "- Scores are relative to screened universe, not absolute",
            "- This is not financial advice",
            ""
        ])

        # News section
        if news_data and results:
            lines.extend(["", "## Recent News", ""])
            for r in results[:5]:
                headlines = news_data.get(r.symbol, [])
                if headlines:
                    lines.extend([f"### {r.symbol}", ""])
                    for h in headlines[:3]:
                        sentiment = h.sentiment if h.sentiment is not None else "N/A"
                        lines.append(f"- **{h.title}** ({h.source}) — Sentiment: {sentiment:.2f}")
                    lines.append("")

        content = "\n".join(lines)
        filepath = self.output_dir / "results.md"

        with open(filepath, "w") as f:
            f.write(content)

        return str(filepath)

    def _generate_analysis(self, results: list[FilterResult]) -> str:
        """Generate insights from results."""
        if not results:
            return "No stocks passed the screening criteria."

        lines = ["### Top Performers", ""]
        for r in results[:5]:
            lines.append(f"**{r.symbol}** (Rank: {r.rank_score:.2f})")
            if r.scores:
                scores_str = ", ".join(f"{k}: {v:.0f}" for k, v in r.scores.items())
                lines.append(f"- {scores_str}")
            lines.append("")

        return "\n".join(lines)

    def save_csv(
        self,
        results: list[FilterResult],
        price_data: dict[str, PriceData],
        fund_data: dict[str, FundamentalData]
    ) -> str:
        """Save results to CSV."""
        filepath = self.output_dir / "results.csv"

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Symbol", "Price", "Change%", "Volume", "MarketCap", "P/E", "P/B",
                "DivYield", "RevenueGrowth", "ROE", "ValueScore", "QualityScore",
                "MomentumScore", "RankScore"
            ])

            for r in results:
                price = price_data.get(r.symbol)
                fund = fund_data.get(r.symbol)

                writer.writerow([
                    r.symbol,
                    price.price if price else "",
                    f"{price.change_pct:.2f}" if price else "",
                    price.volume if price else "",
                    fund.market_cap if fund else "",
                    fund.pe_ratio if fund else "",
                    fund.pb_ratio if fund else "",
                    fund.dividend_yield if fund else "",
                    fund.revenue_growth if fund else "",
                    fund.roe if fund else "",
                    r.scores.get("value_score", ""),
                    r.scores.get("quality_score", ""),
                    r.scores.get("momentum_score", ""),
                    r.rank_score
                ])

        return str(filepath)

    def save_json(
        self,
        results: list[FilterResult],
        price_data: dict[str, PriceData],
        fund_data: dict[str, FundamentalData],
        news_data: Optional[dict[str, list[NewsHeadline]]] = None
    ) -> str:
        """Save full results to JSON."""
        filepath = self.output_dir / "results.json"

        output = []
        for r in results:
            price = price_data.get(r.symbol)
            fund = fund_data.get(r.symbol)
            news = news_data.get(r.symbol) if news_data else None

            item = {
                "symbol": r.symbol,
                "passed": r.passed,
                "failures": r.failures,
                "scores": r.scores,
                "rank_score": r.rank_score,
                "price_data": price.__dict__ if price else None,
                "fundamental_data": fund.__dict__ if fund else None,
                "news": [
                    {"title": h.title, "source": h.source, "url": h.url,
                     "published_at": h.published_at, "sentiment": h.sentiment}
                    for h in (news or [])
                ]
            }
            output.append(item)

        with open(filepath, "w") as f:
            json.dump(output, f, indent=2, default=str)

        return str(filepath)
