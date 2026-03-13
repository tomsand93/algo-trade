"""TDD tests for polymarket_bot.data_loader.

Tests cover:
- load_csv: valid load, sort order, correct values, missing file, malformed rows, Z suffix
- load_json: valid load, sort order, malformed rows, missing file
"""
import json
import textwrap

import pytest

from polymarket_bot.data_loader import load_csv, load_json
from polymarket_bot.models import MarketState

FIXTURE_CSV = "data/historical/fixture_mean_reversion.csv"


# ---------------------------------------------------------------------------
# load_csv
# ---------------------------------------------------------------------------

class TestLoadCSV:
    def test_load_csv_returns_list_of_market_states(self):
        rows = load_csv(FIXTURE_CSV)
        assert len(rows) > 0
        for row in rows:
            assert isinstance(row, MarketState)

    def test_load_csv_sorted_by_timestamp(self):
        rows = load_csv(FIXTURE_CSV)
        timestamps = [r.timestamp for r in rows]
        assert timestamps == sorted(timestamps)

    def test_load_csv_correct_values_first_row(self):
        rows = load_csv(FIXTURE_CSV)
        first = rows[0]
        assert first.market_id == "0xfixture01"
        assert first.yes_price == pytest.approx(0.50, abs=0.001)

    def test_load_csv_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_csv("nonexistent_file_that_does_not_exist.csv")

    def test_load_csv_skips_malformed_rows(self, tmp_path):
        """A row with an invalid yes_price should be skipped, not raise."""
        csv_content = textwrap.dedent("""\
            market_id,question,yes_price,no_price,volume_24h,timestamp
            0xgood01,Good market,0.60,0.40,5000.0,2024-01-15T10:00:00+00:00
            0xbad01,Bad market,INVALID,0.40,5000.0,2024-01-15T11:00:00+00:00
            0xgood02,Good market 2,0.55,0.45,5000.0,2024-01-15T12:00:00+00:00
        """)
        csv_file = tmp_path / "test_malformed.csv"
        csv_file.write_text(csv_content)
        rows = load_csv(str(csv_file))
        assert len(rows) == 2
        assert all(isinstance(r, MarketState) for r in rows)
        market_ids = [r.market_id for r in rows]
        assert "0xbad01" not in market_ids

    def test_load_csv_timestamp_z_suffix(self, tmp_path):
        """Timestamp ending in Z (not +00:00) must load without error."""
        csv_content = textwrap.dedent("""\
            market_id,question,yes_price,no_price,volume_24h,timestamp
            0xtest01,Test market,0.50,0.50,1000.0,2024-01-15T10:00:00Z
        """)
        csv_file = tmp_path / "test_z_suffix.csv"
        csv_file.write_text(csv_content)
        rows = load_csv(str(csv_file))
        assert len(rows) == 1
        assert rows[0].market_id == "0xtest01"


# ---------------------------------------------------------------------------
# load_json
# ---------------------------------------------------------------------------

class TestLoadJSON:
    def test_load_json_array_returns_list(self, tmp_path):
        data = [
            {
                "market_id": "0xjson01",
                "question": "Will it rain?",
                "yes_price": 0.60,
                "no_price": 0.40,
                "volume_24h": 3000.0,
                "timestamp": "2024-01-15T10:00:00+00:00",
            },
            {
                "market_id": "0xjson01",
                "question": "Will it rain?",
                "yes_price": 0.65,
                "no_price": 0.35,
                "volume_24h": 3000.0,
                "timestamp": "2024-01-15T11:00:00+00:00",
            },
            {
                "market_id": "0xjson01",
                "question": "Will it rain?",
                "yes_price": 0.55,
                "no_price": 0.45,
                "volume_24h": 3000.0,
                "timestamp": "2024-01-15T12:00:00+00:00",
            },
        ]
        json_file = tmp_path / "test_data.json"
        json_file.write_text(json.dumps(data))
        rows = load_json(str(json_file))
        assert len(rows) == 3
        assert all(isinstance(r, MarketState) for r in rows)

    def test_load_json_sorted_by_timestamp(self, tmp_path):
        """Data provided out of order should be returned sorted ascending."""
        data = [
            {
                "market_id": "0xjson02",
                "question": "Test?",
                "yes_price": 0.60,
                "no_price": 0.40,
                "volume_24h": 1000.0,
                "timestamp": "2024-01-15T12:00:00+00:00",  # later
            },
            {
                "market_id": "0xjson02",
                "question": "Test?",
                "yes_price": 0.55,
                "no_price": 0.45,
                "volume_24h": 1000.0,
                "timestamp": "2024-01-15T10:00:00+00:00",  # earlier
            },
        ]
        json_file = tmp_path / "test_sort.json"
        json_file.write_text(json.dumps(data))
        rows = load_json(str(json_file))
        timestamps = [r.timestamp for r in rows]
        assert timestamps == sorted(timestamps)

    def test_load_json_skips_malformed_rows(self, tmp_path):
        """A row with an invalid yes_price should be skipped."""
        data = [
            {
                "market_id": "0xgood01",
                "question": "Good?",
                "yes_price": 0.60,
                "no_price": 0.40,
                "volume_24h": 1000.0,
                "timestamp": "2024-01-15T10:00:00+00:00",
            },
            {
                "market_id": "0xbad01",
                "question": "Bad?",
                "yes_price": "INVALID",
                "no_price": 0.40,
                "volume_24h": 1000.0,
                "timestamp": "2024-01-15T11:00:00+00:00",
            },
        ]
        json_file = tmp_path / "test_malformed.json"
        json_file.write_text(json.dumps(data))
        rows = load_json(str(json_file))
        assert len(rows) == 1
        assert rows[0].market_id == "0xgood01"

    def test_load_json_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_json("nonexistent_file_that_does_not_exist.json")
