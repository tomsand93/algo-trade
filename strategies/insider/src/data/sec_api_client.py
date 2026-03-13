"""
SEC API client for fetching insider trading data.

Supports:
1. SEC-API.io (recommended) - structured JSON API
2. SEC EDGAR (fallback) - direct scraping/parsing
"""
import os
import logging
from datetime import date, timedelta
from typing import List, Optional, Dict, Any
import time
import json

import requests

logger = logging.getLogger(__name__)


class SECAPIClient:
    """
    Client for SEC-API.io insider trading endpoint.

    Requires SEC_API_KEY environment variable.
    """

    BASE_URL = "https://api.sec-api.io"
    INSIDER_API = f"{BASE_URL}/insider-trading"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize SEC API client.

        Args:
            api_key: SEC-API.io API key. If None, reads from SEC_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("SEC_API_KEY")
        if not self.api_key:
            logger.warning("SEC_API_KEY not found. SEC-API client will not function.")

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": self.api_key,  # SEC-API uses key directly, NOT "Bearer {key}"
            "Content-Type": "application/json"
        })
        self._last_request_time = 0
        self._min_request_interval = 1.0  # Rate limiting (1 second between requests)

    def _rate_limit(self):
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def fetch_insider_trades(
        self,
        start_date: date,
        end_date: date,
        ticker: Optional[str] = None,
        transaction_code: str = "P"
    ) -> List[Dict[str, Any]]:
        """
        Fetch insider trades for a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            ticker: Optional ticker filter
            transaction_code: Transaction code filter (default "P" for purchases)

        Returns:
            List of insider trade dictionaries
        """
        if not self.api_key:
            raise ValueError("SEC_API_KEY is required")

        queries = self._build_query(start_date, end_date, ticker, transaction_code)

        # Extract individual transactions from each filing
        all_transactions = []
        skipped_code = 0

        for query in queries:
            try:
                self._rate_limit()
                response = self.session.post(
                    self.INSIDER_API,
                    json=query,
                    timeout=30
                )
                response.raise_for_status()

                data = response.json()
                transactions = data.get("transactions", [])

                logger.debug(f"Fetched {len(transactions)} transaction filings for query")

                for filing in transactions:
                    # Get ticker from issuer
                    ticker_sym = filing.get("issuer", {}).get("tradingSymbol", "")
                    if not ticker_sym:
                        continue

                filing_date_str = filing.get("filedAt", "")
                try:
                    if filing_date_str:
                        filing_date = date.fromisoformat(filing_date_str.split("T")[0])
                    else:
                        continue
                except:
                    continue

                # Get reporting owner info
                owner = filing.get("reportingOwner", {})
                insider_name = owner.get("name", "Unknown")

                # Process non-derivative transactions (stocks)
                non_deriv = filing.get("nonDerivativeTable", {})
                for txn in non_deriv.get("transactions", []):
                    # Filter by transaction code
                    coding = txn.get("coding", {})
                    txn_code = coding.get("code", "")

                    # Process open market purchases (P) and option exercises (M)
                    # M = Option exercises are valid buys (insider chose to exercise)
                    # Also include A (acquisition) codes
                    if txn_code not in ["P", "M", "A"]:
                        skipped_code += 1
                        continue

                    # For insider buy signals, we only want purchases (acquisition)
                    acquired_disposed = txn.get("amounts", {}).get("acquiredDisposedCode", "")
                    if acquired_disposed != "A":  # Only acquisitions (buys)
                        skipped_code += 1
                        continue

                    amounts = txn.get("amounts", {})
                    shares = amounts.get("shares", 0)
                    price_ref = amounts.get("pricePerShare", None)

                    # Skip if no price data (footnote reference)
                    if price_ref and isinstance(price_ref, str):
                        skipped_code += 1
                        continue

                    # Calculate total value
                    price = float(amounts.get("pricePerShare", 0)) if isinstance(amounts.get("pricePerShare"), (int, float)) else None
                    total_value = shares * price if price else 0

                    # For option exercises (M codes), price is often None (in footnotes)
                    # Include these transactions but mark value as 0 for now
                    # The signal generator can filter by share count or fetch market prices
                    is_option_exercise = (txn_code == "M")

                    # Skip if value is 0 or negative (unless it's an option exercise)
                    if total_value <= 0 and not is_option_exercise:
                        skipped_code += 1
                        continue

                    transaction = {
                        "ticker": ticker_sym,
                        "filing_date": filing_date.isoformat(),
                        "filing_timestamp": filing_date_str,
                        "insiders": [{
                            "name": insider_name,
                            "transactions": [{
                                "transaction_date": txn.get("transactionDate", filing_date.isoformat()),
                                "transaction_code": txn_code,  # Preserve actual code (P, M, A)
                                "acquisition_disposition": "A",
                                "shares": str(shares),
                                "price_per_share": str(price) if price else "0",
                                "total_value": str(int(total_value)) if total_value > 0 else "0"
                            }]
                        }]
                    }
                    all_transactions.append(transaction)

            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to fetch SEC data for query: {e}")
                continue

        logger.info(f"Fetched {len(all_transactions)} buy transactions total, skipped {skipped_code}")
        return all_transactions

    def _build_query(
        self,
        start_date: date,
        end_date: date,
        ticker: Optional[str],
        transaction_code: str
    ) -> List[Dict[str, Any]]:
        """Build SEC-API queries using Lucene syntax."""
        # SEC-API.io requires at least one field query. Use a broad query if no ticker specified.
        # We'll query multiple popular tickers if no ticker is specified.

        # Common stock tickers to query if none specified
        default_tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM",
            "V", "WMT", "DIS", "NFLX", "CRM", "AMD", "ABBV", "INTC", "AMD"
        ]

        # Build Lucene query string
        query_parts = []

        # Add date range in Lucene format
        date_range = f"filedAt:[{start_date.isoformat()} TO {end_date.isoformat()}]"
        query_parts.append(date_range)

        # Add ticker filter(s)
        if ticker:
            tickers_to_query = [ticker.upper()]
        else:
            tickers_to_query = default_tickers

        # Build queries for each ticker
        queries = []
        for tk in tickers_to_query:
            ticker_part = f"issuer.tradingSymbol:{tk}"
            query_parts_with_ticker = query_parts + [ticker_part]
            query_string = " AND ".join(query_parts_with_ticker)
            queries.append({
                "query": query_string,
                "from": 0,
                "size": 50,  # SEC-API.io free tier max
                "sort": [{"filedAt": "desc"}]
            })

        return queries

    def fetch_by_ticker(self, ticker: str, lookback_days: int = 365) -> List[Dict[str, Any]]:
        """
        Fetch recent insider trades for a specific ticker.

        Args:
            ticker: Stock ticker
            lookback_days: Days to look back from today

        Returns:
            List of insider trade dictionaries
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)

        return self.fetch_insider_trades(start_date, end_date, ticker)


class EdgarClient:
    """
    Client for SEC EDGAR direct access.

    This is a fallback if SEC-API.io is not available.
    Requires EDGAR_USER_AGENT environment variable.
    """

    BASE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"

    def __init__(self, user_agent: Optional[str] = None):
        """
        Initialize EDGAR client.

        Args:
            user_agent: User agent string. EDGAR requires a contact email.
                       Format: "YourName/1.0 (your@email.com)"
        """
        self.user_agent = user_agent or os.getenv("EDGAR_USER_AGENT", "")
        if not self.user_agent:
            logger.warning("EDGAR_USER_AGENT not set. EDGAR requests may be blocked.")

        self.session = requests.Session()
        if self.user_agent:
            self.session.headers.update({"User-Agent": self.user_agent})

        self._last_request_time = 0
        self._min_request_interval = 0.2  # EDGAR rate limit

    def _rate_limit(self):
        """Apply rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def fetch_filings(
        self,
        ticker: str,
        filing_type: str = "4",
        count: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Fetch filings from EDGAR for a ticker.

        Args:
            ticker: Stock ticker
            filing_type: Filing type (default "4" for Form 4)
            count: Number of recent filings to fetch

        Returns:
            List of filing metadata
        """
        params = {
            "action": "getcompany",
            "CIK": ticker,
            "type": filing_type,
            "count": count,
            "output": "atom"
        }

        try:
            self._rate_limit()
            response = self.session.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()

            # Parse the Atom feed
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.content)

            filings = []
            for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                filing = {
                    "title": entry.findtext("{http://www.w3.org/2005/Atom}title", ""),
                    "link": entry.findtext("{http://www.w3.org/2005/Atom}link/@href", ""),
                    "filing_date": entry.findtext("{http://www.w3.org/2005/Atom}updated", ""),
                }
                filings.append(filing)

            return filings

        except Exception as e:
            logger.error(f"Failed to fetch EDGAR filings: {e}")
            return []

    def fetch_filing_xml(self, accession_number: str, cik: str) -> Optional[str]:
        """
        Fetch the XML content of a specific filing.

        Args:
            accession_number: Filing accession number
            cik: Central Index Key

        Returns:
            XML content as string
        """
        # Format accession number for URL (remove dashes)
        clean_accession = accession_number.replace("-", "")

        # EDGAR filing URL pattern
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{clean_accession}.txt"

        try:
            self._rate_limit()
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text

        except Exception as e:
            logger.error(f"Failed to fetch filing XML: {e}")
            return None


def download_insider_data(
    start_date: date,
    end_date: date,
    output_path: str,
    source: str = "secapi"
) -> None:
    """
    Download and cache insider trading data for a date range.

    Args:
        start_date: Start date
        end_date: End date
        output_path: Path to save cached data
        source: Data source ("secapi" or "edgar")
    """
    if source == "secapi":
        client = SECAPIClient()
    else:
        client = EdgarClient()

    logger.info(f"Downloading insider data from {start_date} to {end_date}")

    transactions = client.fetch_insider_trades(start_date, end_date)

    # Save to file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(transactions, f, indent=2, default=str)

    logger.info(f"Saved {len(transactions)} transactions to {output_path}")


def load_cached_data(cache_path: str) -> List[Dict]:
    """Load cached insider data from file."""
    try:
        with open(cache_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Cache file not found: {cache_path}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse cache file: {e}")
        return []
