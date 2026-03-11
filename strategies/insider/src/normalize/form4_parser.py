"""
Parse SEC Form 4 filings into normalized InsiderTransaction records.

Supports two data sources:
1. SEC-API.io structured JSON (recommended)
2. SEC EDGAR XML parsing (fallback)
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
import re

from .schema import InsiderTransaction, TransactionCode, TransactionType

logger = logging.getLogger(__name__)


class Form4Parser:
    """Parse SEC Form 4 data from various sources."""

    @staticmethod
    def from_secapi_json(data: Dict[str, Any]) -> List[InsiderTransaction]:
        """
        Parse Form 4 from SEC-API.io structured JSON.

        Expected structure:
        {
            "ticker": "AAPL",
            "filing_date": "2024-01-15",
            "filing_timestamp": "2024-01-15T16:30:00Z",
            "insiders": [
                {
                    "name": "John Doe",
                    "transactions": [
                        {
                            "transaction_date": "2024-01-13",
                            "transaction_code": "P",
                            "acquisition_disposition": "A",
                            "shares": "1000",
                            "price_per_share": "150.25",
                            "total_value": "150250"
                        }
                    ]
                }
            ]
        }
        """
        transactions = []

        try:
            ticker = data.get("ticker", "").strip().upper()
            if not ticker:
                logger.warning("Skipping entry with missing ticker")
                return []

            filing_date_str = data.get("filing_date", "")
            filing_date = date.fromisoformat(filing_date_str) if filing_date_str else date.today()

            filing_timestamp = None
            filing_ts_str = data.get("filing_timestamp")
            if filing_ts_str:
                try:
                    filing_timestamp = datetime.fromisoformat(filing_ts_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            insiders = data.get("insiders", [])
            for insider in insiders:
                insider_name = insider.get("name", "Unknown").strip()
                txn_list = insider.get("transactions", [])

                for txn in txn_list:
                    try:
                        transaction = Form4Parser._parse_transaction_dict(
                            ticker, insider_name, filing_date, filing_timestamp, txn
                        )
                        if transaction:
                            transactions.append(transaction)
                    except Exception as e:
                        logger.debug(f"Failed to parse transaction: {e}")
                        continue

        except Exception as e:
            logger.error(f"Failed to parse Form4 JSON: {e}")

        return transactions

    @staticmethod
    def _parse_transaction_dict(
        ticker: str,
        insider_name: str,
        filing_date: date,
        filing_timestamp: Optional[datetime],
        txn: Dict[str, Any]
    ) -> Optional[InsiderTransaction]:
        """Parse a single transaction dictionary."""
        txn_date_str = txn.get("transaction_date", "")
        if not txn_date_str:
            return None

        try:
            transaction_date = date.fromisoformat(txn_date_str)
        except ValueError:
            return None

        code = txn.get("transaction_code", "")
        txn_type = txn.get("acquisition_disposition", "")

        shares_str = txn.get("shares", "0")
        price_str = txn.get("price_per_share", "0")
        value_str = txn.get("total_value", "")

        try:
            shares = Decimal(str(shares_str))
            price = Decimal(str(price_str)) if price_str else None
            total_value = Decimal(str(value_str)) if value_str else None
        except (ValueError, TypeError):
            return None

        return InsiderTransaction(
            ticker=ticker,
            insider_name=insider_name,
            transaction_date=transaction_date,
            filing_date=filing_date,
            transaction_code=code,
            transaction_type=txn_type,
            shares=shares,
            price_per_share=price,
            total_value=total_value,
            filing_timestamp=filing_timestamp,
        )

    @staticmethod
    def from_edgar_xml(xml_str: str, ticker: str) -> List[InsiderTransaction]:
        """
        Parse Form 4 from SEC EDGAR XML format.

        This is a simplified parser for the standard EDGAR Form 4 XML structure.
        For production, consider using a more robust XML parser.
        """
        transactions = []
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(xml_str)

            # Extract filing info
            header = root.find(".//header")
            filing_date_str = ""
            if header is not None:
                filing_date_elem = header.find(".//FILED")
                if filing_date_elem is not None:
                    filing_date_str = filing_date_elem.text

            filing_date = date.fromisoformat(filing_date_str) if filing_date_str else date.today()

            # Find non-derivative transactions (Table II)
            for txn_table in root.findall(".//nonDerivativeTransaction"):
                try:
                    transaction = Form4Parser._parse_edgar_transaction(txn_table, ticker, filing_date)
                    if transaction:
                        transactions.append(transaction)
                except Exception as e:
                    logger.debug(f"Failed to parse EDGAR transaction: {e}")
                    continue

        except ET.ParseError as e:
            logger.error(f"Failed to parse EDGAR XML: {e}")

        return transactions

    @staticmethod
    def _parse_edgar_transaction(txn_elem, ticker: str, filing_date: date) -> Optional[InsiderTransaction]:
        """Parse a single transaction from EDGAR XML."""
        # Get transaction date
        date_elem = txn_elem.find(".//transactionDate/value")
        if date_elem is None or date_elem.text is None:
            return None
        transaction_date = date.fromisoformat(date_elem.text)

        # Get transaction code
        code_elem = txn_elem.find(".//transactionCoding/transactionCode")
        transaction_code = code_elem.text if code_elem is not None else ""

        # Get transaction type (acquisition/disposition)
        type_elem = txn_elem.find(".//transactionAcquiredDisposedCode/value")
        transaction_type = type_elem.text if type_elem is not None else ""

        # Get amounts
        amount_elem = txn_elem.find(".//transactionAmounts/transactionShares/value")
        price_elem = txn_elem.find(".//transactionAmounts/transactionPricePerShare/value")

        shares = Decimal(amount_elem.text) if amount_elem is not None and amount_elem.text else Decimal("0")
        price = Decimal(price_elem.text) if price_elem is not None and price_elem.text else None

        # Try to get total value
        total_value_elem = txn_elem.find(".//transactionAmounts/transactionTotalValue/value")
        total_value = Decimal(total_value_elem.text) if total_value_elem is not None and total_value_elem.text else None

        # Insider name (try to get from owner)
        insider_name = "Unknown"
        owner_name = txn_elem.find(".//ownerName")
        if owner_name is not None:
            insider_name = owner_name.text

        return InsiderTransaction(
            ticker=ticker,
            insider_name=insider_name,
            transaction_date=transaction_date,
            filing_date=filing_date,
            transaction_code=transaction_code,
            transaction_type=transaction_type,
            shares=shares,
            price_per_share=price,
            total_value=total_value,
            filing_timestamp=None,
        )


def normalize_transactions(data: List[Dict], source: str = "secapi") -> List[InsiderTransaction]:
    """
    Normalize a list of transaction dictionaries into InsiderTransaction objects.

    Args:
        data: List of transaction dictionaries
        source: Data source format ("secapi" or "edgar")

    Returns:
        List of normalized InsiderTransaction objects
    """
    all_transactions = []

    for entry in data:
        if source == "secapi":
            transactions = Form4Parser.from_secapi_json(entry)
        elif source == "edgar":
            xml_str = entry.get("xml", "") if isinstance(entry, dict) else str(entry)
            ticker = entry.get("ticker", "") if isinstance(entry, dict) else ""
            transactions = Form4Parser.from_edgar_xml(xml_str, ticker)
        else:
            raise ValueError(f"Unknown source: {source}")

        all_transactions.extend(transactions)

    return all_transactions
