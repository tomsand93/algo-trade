from dataclasses import dataclass


@dataclass
class StrategyConfig:
    # Trading period
    start_date: str = "2025-01-01"
    stop_date: str = "2026-01-01"

    # Strategy settings
    enable_mfi: bool = False
    enable_ao: bool = False
    lowest_bars: int = 7

    # DCA layer thresholds (percent drop from layer1)
    layer2_threshold_pct: float = 4.0
    layer3_threshold_pct: float = 10.0
    layer4_threshold_pct: float = 22.0

    # Position sizing
    position_size_multiplier: float = 2.0

    # Take profit
    takeprofit_num_atr: float = 2.0

    # Strategy mechanics (Pine Script defaults)
    initial_capital: float = 10000.0
    pyramiding: int = 4
    commission_pct: float = 0.1       # percent per trade
    slippage_ticks: int = 5
    tick_size: float = 0.01           # BTC tick size on Binance

    # Alligator parameters
    jaw_length: int = 13
    jaw_offset: int = 8
    teeth_length: int = 8
    teeth_offset: int = 5
    lips_length: int = 5
    lips_offset: int = 3

    # ATR
    atr_length: int = 14

    # Data fetching
    symbol: str = "BTC/USDT"
    timeframe: str = "30m"
    warmup_start: str = "2024-10-01"  # extra bars for indicator warmup

    @property
    def slippage(self) -> float:
        return self.slippage_ticks * self.tick_size
