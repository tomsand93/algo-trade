import pandas as pd

from src.data_fetcher import validate_data_coverage


def test_validate_data_coverage_handles_tz_aware_index_with_naive_dates():
    index = pd.to_datetime(
        [
            "2024-01-15 09:30:00",
            "2024-01-15 09:31:00",
            "2024-01-15 16:00:00",
        ]
    ).tz_localize("America/New_York")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.5, 101.0],
            "high": [101.0, 101.5, 101.2],
            "low": [99.5, 100.2, 100.8],
            "close": [100.5, 101.0, 101.1],
            "volume": [1000, 1200, 900],
        },
        index=index,
    )

    result = validate_data_coverage(
        df=df,
        symbol="AAPL",
        timeframe="1Min",
        start_date="2024-01-15",
        end_date="2024-01-15",
    )

    assert result["valid"] is True
    assert result["issues"] == []
