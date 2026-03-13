"""Configuration management for orderbook strategy."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Config:
    """Strategy configuration."""

    # Data parameters
    tick_size: float = 0.01
    symbol: str = "BTC/USD"

    # Range and depth
    range_window_s: int = 60
    depth_levels: int = 5

    # Detection windows
    sweep_window_s: int = 2
    absorption_window_s: int = 3
    delta_window_s: int = 1

    # Thresholds
    imb_threshold: float = 0.15
    sweep_min_notional: float = 10000
    depth_drop_pct: float = 0.3
    delta_abs_min_notional: float = 8000  # Use notional for consistency with sweep (delta * price)

    # Entry
    retest_ticks: int = 2

    # Exits
    stop_ticks: int = 2
    time_stop_s: int = 60
    flip_confirm_s: int = 2

    # Execution
    fee_per_share_or_contract: float = 0.0
    slippage_ticks: int = 1
    latency_ms: int = 100

    # Probability / Distribution
    horizon_s: int = 10
    dist_type: str = "normal"
    dist_lookback: int = 2000
    hist_bins: int = 60
    min_dist_samples: int = 200
    sigma_floor: float = 1.0e-6
    p_threshold: float = 0.57
    use_state_conditioning: bool = True

    # Position sizing
    base_qty: float = 1.0
    use_prob_sizing: bool = True
    edge_ref: float = 0.10
    max_mult: float = 3.0

    # Liquidity wall detection
    wall_mult: float = 3.0
    wall_lookback_s: int = 5

    # Logging
    log_level: str = "INFO"
    log_trades: bool = True
    log_signals: bool = True

    @classmethod
    def from_yaml(cls, path: Optional[Path] = None) -> "Config":
        """Load config from YAML file, fall back to defaults."""
        if path is None or not path.exists():
            return cls()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
