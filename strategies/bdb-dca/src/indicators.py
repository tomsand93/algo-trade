"""
Indicator calculations matching Pine Script exactly.

Key details:
- SMMA (Smoothed Moving Average) uses recursive formula: (prev*(len-1)+src)/len
  with SMA as the seed value on the first bar where we have enough data.
- Alligator shifts are BACKWARD: [N] in Pine means N bars ago.
  jaw = smma(hl2,13)[8], teeth = smma(hl2,8)[5], lips = smma(hl2,5)[3]
- ATR uses RMA/Wilder smoothing (same formula as SMMA).
- AO = SMA(hl2,5) - SMA(hl2,34).
- MFI = 1e9 * (high-low) / volume. Guard division by zero.
"""

from collections import deque
import math
from typing import Optional

from .models import Bar


class IndicatorState:
    """Holds all persistent indicator state across bars."""

    def __init__(self, jaw_length=13, jaw_offset=8,
                 teeth_length=8, teeth_offset=5,
                 lips_length=5, lips_offset=3,
                 atr_length=14, lowest_bars=7):
        # Alligator params
        self.jaw_length = jaw_length
        self.jaw_offset = jaw_offset
        self.teeth_length = teeth_length
        self.teeth_offset = teeth_offset
        self.lips_length = lips_length
        self.lips_offset = lips_offset

        # SMMA states
        self.smma_jaw: Optional[float] = None
        self.smma_teeth: Optional[float] = None
        self.smma_lips: Optional[float] = None

        # History deques for shifted Alligator values
        # Need to store enough past SMMA values to look back by offset
        self.smma_jaw_history: deque = deque(maxlen=jaw_offset + 1)
        self.smma_teeth_history: deque = deque(maxlen=teeth_offset + 1)
        self.smma_lips_history: deque = deque(maxlen=lips_offset + 1)

        # SMA buffers for SMMA initialization
        self._jaw_src_buf: list = []
        self._teeth_src_buf: list = []
        self._lips_src_buf: list = []
        self._jaw_initialized = False
        self._teeth_initialized = False
        self._lips_initialized = False

        # ATR state (RMA/Wilder)
        self.atr_length = atr_length
        self.atr_value: Optional[float] = None
        self._atr_tr_buf: list = []
        self._atr_initialized = False
        self._prev_close: Optional[float] = None

        # AO state: need SMA(hl2, 5) and SMA(hl2, 34)
        self._ao_hl2_buf: deque = deque(maxlen=34)
        self.ao_value: Optional[float] = None
        self.ao_prev: Optional[float] = None
        self.ao_diff: Optional[float] = None

        # MFI state
        self.mfi_value: Optional[float] = None
        self.prev_mfi: Optional[float] = None
        self.prev_volume: Optional[float] = None
        self.squatbar: bool = False
        self.squatbar_history: deque = deque(maxlen=3)

        # Lowest bar state
        self.lowest_bars = lowest_bars
        self._low_buf: deque = deque(maxlen=max(lowest_bars, 1))

        # Current shifted Alligator values
        self.jaw: Optional[float] = None
        self.teeth: Optional[float] = None
        self.lips: Optional[float] = None

        # Bar counter
        self.bar_index = 0

    def update(self, bar: Bar):
        """Process one bar and update all indicators."""
        hl2 = bar.hl2

        # --- SMMA calculations ---
        self._update_smma_jaw(hl2)
        self._update_smma_teeth(hl2)
        self._update_smma_lips(hl2)

        # --- Shifted Alligator values ---
        # [N] in Pine = N bars ago = look back N positions in history
        # After appending current SMMA, history[-1] is current,
        # history[-(offset+1)] is offset bars ago
        if len(self.smma_jaw_history) > self.jaw_offset:
            self.jaw = self.smma_jaw_history[-(self.jaw_offset + 1)]
        else:
            self.jaw = None

        if len(self.smma_teeth_history) > self.teeth_offset:
            self.teeth = self.smma_teeth_history[-(self.teeth_offset + 1)]
        else:
            self.teeth = None

        if len(self.smma_lips_history) > self.lips_offset:
            self.lips = self.smma_lips_history[-(self.lips_offset + 1)]
        else:
            self.lips = None

        # --- ATR (RMA/Wilder smoothing) ---
        self._update_atr(bar)

        # --- AO ---
        self._update_ao(hl2)

        # --- MFI ---
        self._update_mfi(bar)

        # --- Lowest bar ---
        self._low_buf.append(bar.low)

        self.bar_index += 1

    def _update_smma_jaw(self, src: float):
        if not self._jaw_initialized:
            self._jaw_src_buf.append(src)
            if len(self._jaw_src_buf) == self.jaw_length:
                self.smma_jaw = sum(self._jaw_src_buf) / self.jaw_length
                self.smma_jaw_history.append(self.smma_jaw)
                self._jaw_initialized = True
            else:
                self.smma_jaw_history.append(None)
        else:
            self.smma_jaw = (self.smma_jaw * (self.jaw_length - 1) + src) / self.jaw_length
            self.smma_jaw_history.append(self.smma_jaw)

    def _update_smma_teeth(self, src: float):
        if not self._teeth_initialized:
            self._teeth_src_buf.append(src)
            if len(self._teeth_src_buf) == self.teeth_length:
                self.smma_teeth = sum(self._teeth_src_buf) / self.teeth_length
                self.smma_teeth_history.append(self.smma_teeth)
                self._teeth_initialized = True
            else:
                self.smma_teeth_history.append(None)
        else:
            self.smma_teeth = (self.smma_teeth * (self.teeth_length - 1) + src) / self.teeth_length
            self.smma_teeth_history.append(self.smma_teeth)

    def _update_smma_lips(self, src: float):
        if not self._lips_initialized:
            self._lips_src_buf.append(src)
            if len(self._lips_src_buf) == self.lips_length:
                self.smma_lips = sum(self._lips_src_buf) / self.lips_length
                self.smma_lips_history.append(self.smma_lips)
                self._lips_initialized = True
            else:
                self.smma_lips_history.append(None)
        else:
            self.smma_lips = (self.smma_lips * (self.lips_length - 1) + src) / self.lips_length
            self.smma_lips_history.append(self.smma_lips)

    def _update_atr(self, bar: Bar):
        if self._prev_close is None:
            # First bar: no TR yet
            self._prev_close = bar.close
            return

        # True Range
        tr = max(
            bar.high - bar.low,
            abs(bar.high - self._prev_close),
            abs(bar.low - self._prev_close)
        )

        if not self._atr_initialized:
            self._atr_tr_buf.append(tr)
            if len(self._atr_tr_buf) == self.atr_length:
                self.atr_value = sum(self._atr_tr_buf) / self.atr_length
                self._atr_initialized = True
        else:
            # RMA/Wilder: same as SMMA
            self.atr_value = (self.atr_value * (self.atr_length - 1) + tr) / self.atr_length

        self._prev_close = bar.close

    def _update_ao(self, hl2: float):
        self._ao_hl2_buf.append(hl2)

        buf = list(self._ao_hl2_buf)
        if len(buf) >= 34:
            sma5 = sum(buf[-5:]) / 5.0
            sma34 = sum(buf[-34:]) / 34.0
            new_ao = sma5 - sma34
            self.ao_prev = self.ao_value
            self.ao_value = new_ao
            if self.ao_prev is not None:
                self.ao_diff = self.ao_value - self.ao_prev
            else:
                self.ao_diff = None
        else:
            self.ao_prev = self.ao_value
            self.ao_value = None
            self.ao_diff = None

    def _update_mfi(self, bar: Bar):
        # Save previous values before computing current
        self.prev_mfi = self.mfi_value
        prev_vol = self.prev_volume

        if bar.volume == 0 or bar.volume is None:
            self.mfi_value = None
        else:
            self.mfi_value = 1_000_000_000.0 * (bar.high - bar.low) / bar.volume

        # Squatbar: MFI < prev_MFI and volume > prev_volume
        if (self.mfi_value is not None and self.prev_mfi is not None
                and prev_vol is not None and prev_vol > 0):
            self.squatbar = (self.mfi_value < self.prev_mfi) and (bar.volume > prev_vol)
        else:
            self.squatbar = False

        self.squatbar_history.append(self.squatbar)
        self.prev_volume = bar.volume

    def is_lowest_bar(self, current_low: float) -> bool:
        """Pine: ta.lowest(lowestBars) == low. lowestBars=0 → always false."""
        if self.lowest_bars == 0:
            return False
        buf = list(self._low_buf)
        if len(buf) < self.lowest_bars:
            return False
        window = buf[-self.lowest_bars:]
        return min(window) == current_low

    def is_bullish_reversal_bar(self, bar: Bar) -> bool:
        """close > hl2 and isLowestBar"""
        return bar.close > bar.hl2 and self.is_lowest_bar(bar.low)

    def has_recent_squatbar(self) -> bool:
        """squatbar or squatbar[1] or squatbar[2]"""
        hist = list(self.squatbar_history)
        if len(hist) == 0:
            return False
        # Current bar's squatbar is the last entry
        for i in range(min(3, len(hist))):
            if hist[-(i + 1)]:
                return True
        return False

    def is_true_bullish_reversal(self, bar: Bar, enable_ao: bool, enable_mfi: bool) -> bool:
        """Full reversal detection matching Pine's 4-way if/else."""
        if not self.is_bullish_reversal_bar(bar):
            return False

        # Must be below all Alligator lines
        if self.jaw is None or self.teeth is None or self.lips is None:
            return False
        if not (bar.high < self.jaw and bar.high < self.teeth and bar.high < self.lips):
            return False

        if enable_ao and enable_mfi:
            return (self.ao_diff is not None and self.ao_diff < 0
                    and self.has_recent_squatbar())
        elif enable_ao and not enable_mfi:
            return self.ao_diff is not None and self.ao_diff < 0
        elif not enable_ao and enable_mfi:
            return self.has_recent_squatbar()
        else:
            return True
