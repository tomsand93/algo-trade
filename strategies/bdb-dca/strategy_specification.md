# Bullish Divergent Bar DCA Strategy — Full Specification

## Assumptions

| # | Assumption | Justification |
|---|-----------|---------------|
| A1 | Timeframe = 30-minute candles | Hard constraint |
| A2 | Asset class = crypto spot (Binance-like) | Per instruction |
| A3 | Base currency = USDT | Matches script `currency.USDT` |
| A4 | Commission = 0.1% per side | Matches script `commission_value = 0.1` |
| A5 | Slippage = 5 ticks; default tick = 0.01 USDT → 0.05 USDT per unit | Script uses `slippage = 5`; tick size is asset-dependent; we define slippage as 1 bps (0.01%) per fill as a fallback when tick size is unknown |
| A6 | Initial capital = 10,000 USDT per symbol | Matches script `initial_capital = 10000` |
| A7 | Multi-symbol allocation = equal-weight (capital / N_symbols) at day start | Default; rebalanced daily |
| A8 | Default parameters: lowestBars=7, layer2%=4, layer3%=10, layer4%=22, mult=2.0, atrMult=2.0, enable_AO=false, enable_MFI=false | Match script defaults |
| A9 | "Day" = UTC calendar day 00:00:00.000 to 23:59:59.999 | Default for crypto; no exchange local time needed |
| A10 | Kill-switch daily PnL uses realized PnL only (default); unrealized variant documented as alternative | Realized is conservative and unambiguous |
| A11 | Kill-switch cooldown = 3 calendar days (UTC) | Default chosen; justified below |
| A12 | Pine Script `ta.lowest(length)` with no source argument defaults to source=`low` | Pine v6 behavior |
| A13 | Pending stop-entry orders from `strategy.entry()` persist across bars until filled or replaced by a new call with the same `id` | Pine v6 behavior; no `strategy.cancel()` in the code |
| A14 | `var` inside Pine functions creates per-call-site persistent state | Each of the 3 `smma()` calls maintains its own state |

---

## 1) Strategy Spec (Mechanical)

### 1.1 Indicators and Calculations

#### 1.1.1 SMMA (Smoothed Moving Average)

```
smma(src, length):
    state: smma_val = NaN  (persistent per call-site)
    sma_value = SMA(src, length)
    if isnan(smma_val):
        smma_val = sma_value
    else:
        smma_val = (smma_val * (length - 1) + src) / length
    return smma_val
```

- **Initialization**: On the first bar where SMA can be computed (bar index >= length-1), `smma_val` is set to SMA.
- **Recursion**: Standard exponential-style smoothing with decay = (length-1)/length.
- **Python note**: Must maintain 3 separate SMMA states for the 3 Alligator lines.

#### 1.1.2 Williams Alligator Lines

```
jaw   = smma(hl2, 13)[8]    # 13-period SMMA of (H+L)/2, looked back 8 bars
teeth = smma(hl2, 8)[5]     # 8-period SMMA of (H+L)/2, looked back 5 bars
lips  = smma(hl2, 5)[3]     # 5-period SMMA of (H+L)/2, looked back 3 bars
```

**Meaning of `[N]`**: `expr[N]` in Pine = value of `expr` from N bars ago. So:
- `jaw` at bar `i` = SMMA_13 computed at bar `i-8`
- `teeth` at bar `i` = SMMA_8 computed at bar `i-5`
- `lips` at bar `i` = SMMA_5 computed at bar `i-3`

These are **backward shifts** (lagged values), NOT future projections. In a Python array: `jaw[i] = smma13_array[i - 8]` (index < 0 → NaN).

#### 1.1.3 ATR (Average True Range)

```
atr = ATR(14)
```

Standard 14-period ATR using RMA (Wilder smoothing) of True Range.
- TR = max(high - low, abs(high - close[1]), abs(low - close[1]))
- ATR = RMA(TR, 14)

#### 1.1.4 Awesome Oscillator (AO)

```
ao   = SMA(hl2, 5) - SMA(hl2, 34)
diff = ao - ao[1]
```

- `hl2` = (high + low) / 2
- `diff < 0` means AO is declining (bearish momentum confirmation).

#### 1.1.5 Market Facilitation Index (MFI) States

```
MFI      = 1e9 * (high - low) / volume
PreMFI   = 1e9 * (high[1] - low[1]) / volume[1]

greenbar = (MFI > PreMFI) and (volume > volume[1])
fadebar  = (MFI < PreMFI) and (volume < volume[1])
fakebar  = (MFI > PreMFI) and (volume < volume[1])
squatbar = (MFI < PreMFI) and (volume > volume[1])
```

Only `squatbar` is used in signal logic. The 1e9 multiplier is cosmetic (cancels in comparison).

**Edge case — volume = 0**: If `volume == 0` on bar `i`, MFI = ±infinity or NaN (division by zero). If `volume[1] == 0`, PreMFI = ±infinity or NaN. In either case, comparisons involving NaN yield false → `squatbar = false`. **Python implementation must guard against division by zero**: if volume == 0, set MFI = NaN, which forces squatbar = false.

#### 1.1.6 Lowest Bar Rule

```
isLowestBar = ta.lowest(low, lowestBars) == low
```

Returns `true` when the current bar's low is the minimum low over the trailing `lowestBars` bars (inclusive of current bar).

**Edge cases**:
- `lowestBars = 0`: `ta.lowest(low, 0)` returns NaN → `NaN == low` → false. **No signals ever generated.**
- `lowestBars = 1`: Only checks current bar against itself → always true. **Every bar is "lowest".**
- Multiple bars sharing the same low: `ta.lowest` returns the value; `==` compares values, so all tied bars return true. Pine assigns to the most recent bar (no lookahead), but the equality check means all tied bars qualify.

#### 1.1.7 Base Bullish Reversal Bar

```
isBullishReversalBar() => close > hl2 AND isLowestBar
```

- `close > (high + low) / 2`: close is in the upper half of the bar's range.
- Combined with isLowestBar: this bar made a local low AND closed strong.

---

### 1.2 Signal Conditions for "True Bullish Reversal Bar"

All four toggle combinations share a common base:
```
BASE = isBullishReversalBar() AND high < jaw AND high < teeth AND high < lips
```

The entire bar must be BELOW all three Alligator lines (using `high <` not `close <`).

| enable_AO | enable_MFI | Additional condition |
|-----------|-----------|---------------------|
| true | true | `diff < 0 AND (squatbar[0] OR squatbar[1] OR squatbar[2])` |
| true | false | `diff < 0` |
| false | true | `(squatbar[0] OR squatbar[1] OR squatbar[2])` |
| false | false | *(none — BASE only)* |

**Formal definition**:
```
isTrueBullishReversalBar =
    BASE
    AND (NOT enable_AO OR diff < 0)
    AND (NOT enable_MFI OR (squatbar[0] OR squatbar[1] OR squatbar[2]))
```

**Key detail**: `isTrueBullishReversalBar` is a `var` (persistent) variable. It is reassigned **every bar** by exactly one of the four if-blocks (determined by the constant input toggles). So it reflects the current bar's evaluation only — no stale state carries over.

**Squatbar lookback [0..2]**: Current bar or either of the two preceding bars can be a squat bar. This provides a 3-bar window (~1.5 hours at 30m) for the MFI condition.

---

### 1.3 Entry Logic

#### 1.3.1 Confirmation / Invalidation Level Mechanics

**Setting levels** (on the signal bar):
```
if isTrueBullishReversalBar:
    bullBarConfirmationLevel = high    # of the reversal bar
    bullBarInvalidationLevel = low     # of the reversal bar
```

Both are `var float` (persistent). They hold until explicitly reset.

**Resetting levels** (on subsequent bars):
```
isBullBarInvalidated = crossunder(low, bullBarInvalidationLevel)

if crossover(high, bullBarConfirmationLevel) OR isBullBarInvalidated:
    bullBarConfirmationLevel = NaN
    bullBarInvalidationLevel = NaN
```

- `crossover(high, X)` = `high[1] < X[1] AND high[0] > X[0]` — the high broke above the confirmation level.
- `crossunder(low, X)` = `low[1] > X[1] AND low[0] < X[0]` — the low broke below the invalidation level.
- On the signal bar itself: `high[0] == bullBarConfirmationLevel[0]` (just set), so `high > X` is false (not strictly greater). Same for low. **Levels do NOT reset on the bar they are set.**

**Lifecycle**:
1. Bar N: reversal bar detected → levels set to high_N and low_N.
2. Bar N+1..M: levels persist.
3. Bar M: either (a) high crosses above confirmation → levels reset (entry likely filled), or (b) low crosses below invalidation → levels reset (signal cancelled).
4. If neither happens, levels persist indefinitely until the next reversal bar overwrites them.

#### 1.3.2 Stop Entry Behavior

```
strategy.entry(id='entry1', direction=long, stop=bullBarConfirmationLevel, qty=qty)
```

- This places a **buy-stop order** at `bullBarConfirmationLevel` (the reversal bar's high).
- The order triggers when price trades AT OR ABOVE the stop price.
- **The entry command only executes on bars where `isTrueBullishReversalBar == true`** (within the entry if-block).
- Once placed, the pending order **persists across subsequent bars** until:
  - It fills (high of a subsequent bar >= stop price).
  - A new `strategy.entry('entry1', ...)` call replaces it (new reversal bar while currentLayer == 0).
  - Script ends.
- **There is NO `strategy.cancel()` on invalidation.** If the invalidation level is breached but the pending stop order hasn't filled, the order remains active. This is a code design choice — the stop order can fill AFTER the reversal bar's low has been broken.

**Fill model in Pine**: On bar B where the pending stop at price P exists:
- If `open[B] >= P`: fills at open (gap up).
- If `low[B] < P <= high[B]`: fills at P (intrabar touch).
- If `high[B] < P`: does not fill.

#### 1.3.3 Layer Unlock Rules

**Layer detection** (runs every bar, AFTER order fills are processed):
```
if opentrades == 1 AND opentrades[1] == 0:
    layer1 = position_avg_price     # capture first entry fill price
    currentLayer = 1

if opentrades == 2 AND opentrades[1] == 1:  currentLayer = 2
if opentrades == 3 AND opentrades[1] == 2:  currentLayer = 3
if opentrades == 4 AND opentrades[1] == 3:  currentLayer = 4
```

**End-of-script reset**:
```
if opentrades == 0:
    currentLayer = 0
```

**Threshold computation** (runs every bar):
```
layer2Threshold = layer1 * (100 - layer2ThresholdPercent) / 100
layer3Threshold = layer1 * (100 - layer3ThresholdPercent) / 100
layer4Threshold = layer1 * (100 - layer4ThresholdPercent) / 100
```

With defaults (4%, 10%, 22%): layer2 = layer1 * 0.96, layer3 = layer1 * 0.90, layer4 = layer1 * 0.78.

**Entry conditions for DCA layers**:

| Layer | Condition | Entry |
|-------|-----------|-------|
| 1 (first) | `currentLayer == 0 AND inWindow AND isTrueBullishReversalBar` | stop at bullBarConfirmationLevel |
| 2 | `currentLayer == 1 AND low < layer2Threshold AND inWindow AND isTrueBullishReversalBar` | stop at bullBarConfirmationLevel |
| 3 | `currentLayer == 2 AND low < layer3Threshold AND inWindow AND isTrueBullishReversalBar` | stop at bullBarConfirmationLevel |
| 4 | `currentLayer == 3 AND low < layer4Threshold AND inWindow AND isTrueBullishReversalBar` | stop at bullBarConfirmationLevel |

**Critical nuance**: The `low < layerNThreshold` check only requires price to have **touched** below the threshold during the current bar. The actual entry still uses a **stop order at the reversal bar's high**, which can be significantly above the threshold. So the fill price for layer 2+ is NOT at the threshold — it's at the reversal bar's high (or gap open above it).

**"New reversal bar required"**: Each DCA layer entry requires `isTrueBullishReversalBar == true` on the current bar. This is implicitly enforced — there is no separate flag. A DCA entry cannot happen on a bar that is not itself a valid bullish reversal bar.

#### 1.3.4 Position Sizing Formula (Geometric Weights)

```python
def getLayerEquityQty(mult, layer, price):
    # layer = 0,1,2,3 for entries 1,2,3,4
    sumW = 1.0 + mult + mult**2 + mult**3
    wCur = mult ** layer
    pct  = wCur / sumW
    cap  = equity * pct
    qty  = cap / price
    return qty
```

With default `mult = 2.0`:
- `sumW = 1 + 2 + 4 + 8 = 15`

| Entry | Layer index | Weight | % of equity | Default (10k) |
|-------|------------|--------|-------------|---------------|
| entry1 | 0 | 1 | 6.67% | ~667 USDT |
| entry2 | 1 | 2 | 13.33% | ~1,333 USDT |
| entry3 | 2 | 4 | 26.67% | ~2,667 USDT |
| entry4 | 3 | 8 | 53.33% | ~5,333 USDT |
| **Total** | | **15** | **100%** | **~10,000 USDT** |

**Note**: `equity` is `strategy.equity` (current equity, not initial capital), so sizes scale with PnL. The `price` parameter is `bullBarConfirmationLevel` — the expected fill price for the stop entry.

**Edge case**: If equity has declined significantly by layer 4, the absolute size is smaller, providing natural risk reduction. Conversely, if equity has grown, sizes are larger — this is a feature of the geometric sizing.

---

### 1.4 Exit Logic

#### 1.4.1 Take-Profit Level Computation

```
if opentrades > 0:
    takeProfitLevel = position_avg_price + atr * takeprofitNumAtr
else:
    takeProfitLevel = NaN
```

- `position_avg_price`: volume-weighted average entry price across all open entries.
- `atr`: current bar's 14-period ATR.
- With default `takeprofitNumAtr = 2.0`: TP = avg_price + 2 * ATR(14).

**TP updates every bar** while a position is open. As ATR changes and as new DCA entries shift the average price, the TP level moves. This creates a **dynamic trailing target** that:
- Drops when a new DCA layer enters at a lower price (avg price decreases).
- Adjusts to current volatility (ATR changes).

#### 1.4.2 Exit Orders

```
strategy.exit(id='entry1', from_entry='entry1', limit=takeProfitLevel)
strategy.exit(id='entry2', from_entry='entry2', limit=takeProfitLevel)
strategy.exit(id='entry3', from_entry='entry3', limit=takeProfitLevel)
strategy.exit(id='entry4', from_entry='entry4', limit=takeProfitLevel)
```

- Each entry has its own exit, but they ALL share the same `takeProfitLevel`.
- `strategy.exit()` with `limit` creates/updates a pending limit-sell order.
- Since these calls execute **every bar**, the limit price is **replaced each bar** with the freshly computed `takeProfitLevel`.
- When `high >= takeProfitLevel`, the limit order fills. All layers' exits share the same price, so they all fill on the same bar.

**Practical implication**: The entire stacked position (all DCA layers) exits together at a single bar when price reaches TP. Individual layer exits do not happen independently because they share the same limit price.

**Fill model**: Limit sell fills when `high >= takeProfitLevel`:
- If `open >= takeProfitLevel`: fills at open.
- If `low < takeProfitLevel <= high`: fills at takeProfitLevel.

---

### 1.5 Exit Logic — Order Replacement Model

Each bar, `strategy.exit()` is called with `limit = takeProfitLevel`. In Pine Script, calling `strategy.exit()` with the same `id` replaces the previous pending exit order. So:

1. Bar K: TP = avg_price + ATR_K * 2.0 → exit order placed at this level.
2. Bar K+1: TP recalculated → exit order replaced with new level.
3. This continues until the order fills or position closes.

There is **no stop-loss** in this strategy. The only exit mechanism is the take-profit limit order. Positions can theoretically be held indefinitely if TP is never reached (subject to the trading window end date — but the code has no forced exit at window end either).

---

### 1.6 Known Failure Modes / Edge Cases

| # | Issue | Impact | Mitigation |
|---|-------|--------|------------|
| F1 | **volume = 0** | MFI = Inf or NaN; squatbar comparisons yield false → MFI filter effectively disabled for that bar | Python: guard with `if volume == 0: MFI = NaN` |
| F2 | **lowestBars = 0** | `ta.lowest(low, 0)` = NaN → isLowestBar always false → **zero signals** | Python: validate lowestBars >= 1; if 0, log warning and skip symbol |
| F3 | **NaN propagation for confirmation/invalidation levels** | If no reversal bar has occurred, levels are NaN. `crossover(high, NaN)` and `crossunder(low, NaN)` return false. Stop entry with `stop=NaN` does not fill. All safe — no spurious entries. | No action needed; NaN is handled correctly |
| F4 | **Pending stop survives invalidation** | After low crosses below invalidation level, the pending stop entry is NOT cancelled. If price later rallies above the (stale) confirmation level, the order fills. | This is intentional behavior per code; Python backtest must replicate it |
| F5 | **Intrabar order modeling on 30m candles** | Stop and limit orders are evaluated against OHLC only, not tick data. Multiple orders could theoretically trigger within the same bar; Pine resolves in a fixed priority order (entries before exits). | Python: define explicit priority — process stop entries first, then limit exits, within same bar |
| F6 | **opentrades-based layer detection** | `currentLayer` only updates when opentrades transitions (e.g., 0→1). If two entries fill on the same bar (unlikely with stop orders at different prices but theoretically possible), the transition check `opentrades[1]==0` may miss intermediate states. | Python: process one order per bar at most per entry ID; Pine does this by default |
| F7 | **currentLayer reset at script end** | `if opentrades == 0: currentLayer = 0` runs at line 192, AFTER entry logic. On a bar where the last exit fills (opentrades goes from N→0), the entry logic at lines 159-173 still sees `currentLayer` from the previous state. The reset happens after entries. | Python: replicate this execution order — entries evaluated before end-of-bar layer reset |
| F8 | **No forced close at window end** | `time <= lookBackPeriodStop` prevents new entries but does NOT close existing positions. Positions opened near window end can remain open indefinitely. | For backtest: either force-close at end, or mark as open. Document choice. Default: force-close at last bar of backtest period. |
| F9 | **ATR warmup** | ATR(14) requires 14+ bars. First 14 bars have NaN or partial ATR. TP = avg + NaN = NaN → exit orders have NaN limit → no exits possible. | Ensure sufficient warmup period (at least 34 bars for SMA(hl2,34) in AO). |
| F10 | **layer1 stale after full exit** | `layer1` is set when opentrades transitions 0→1 but is never cleared. After a full exit and re-entry, layer1 is updated to the new entry price. Between full exit and re-entry, layer1 retains the old value but is not used (entry conditions check currentLayer == 0). | Safe; no impact. |

---

## 2) Backtest Design (30m)

### 2.1 Data Requirements

| Field | Specification |
|-------|--------------|
| **Candles** | 30-minute OHLCV |
| **Timezone** | All timestamps in UTC |
| **Day boundary** | UTC 00:00:00.000 to 23:59:59.999 (48 candles per day) |
| **Source** | Binance spot API (or CCXT with Binance) |
| **Format** | `[timestamp_ms, open, high, low, close, volume]` |
| **Minimum history** | 500 bars warmup before first valid signal (covers: 34-bar SMA for AO + 8-bar shift for jaw + ATR warmup). Conservative: start data 1000 bars before trade window start. |
| **Volume** | Quote volume (USDT) preferred; base volume acceptable if converted. |
| **Holidays/gaps** | Crypto trades 24/7; no gap handling needed. Missing candles: forward-fill OHLC from last known bar, volume = 0. |
| **Tick size** | Defined per symbol from exchange info. Used for slippage computation. |

### 2.2 Execution Assumptions

#### 2.2.1 Stop Entries (Buy-Stop Orders)

A pending buy-stop at price P exists. On bar B:

```
if open_B >= P:
    fill_price = open_B + slippage      # gap-up: fill at open + slippage
elif high_B >= P:
    fill_price = P + slippage            # intrabar touch: fill at stop + slippage
else:
    no fill
```

**Slippage model (default)**: `slippage = max(5 * tick_size, fill_price * 0.0001)` — the greater of 5 ticks or 1 bps. This handles both known and unknown tick sizes.

**Justification**: Using the stop price (not midpoint) as fill price is conservative. Adding slippage models the reality that stop orders often fill slightly above the trigger.

#### 2.2.2 Limit Exits (Limit-Sell Orders)

A pending limit-sell at price L exists. On bar B:

```
if open_B >= L:
    fill_price = open_B                  # gap-up: fill at open (favorable)
elif high_B >= L:
    fill_price = L                       # intrabar touch: fill at limit
else:
    no fill
```

**No slippage on limit exits (default)**. Justification: limit orders provide liquidity; in spot markets with reasonable size, limit fills at the posted price are standard. If desired, subtract 1 bps as conservative variant.

#### 2.2.3 Commission Model

```
commission_per_side = 0.1%  (of notional value)
entry_cost = qty * fill_price * 0.001
exit_cost  = qty * fill_price * 0.001
```

Applied to each fill independently (each DCA layer entry and each layer exit).

#### 2.2.4 Pyramiding Handling

- Maximum 4 concurrent entry IDs: `entry1`, `entry2`, `entry3`, `entry4`.
- Each ID can have at most 1 open position.
- New entries with an existing ID replace the pending order (if unfilled) or are rejected (if already filled and position open).
- All 4 exits share the same limit price, updated each bar.

#### 2.2.5 Order Priority Within a Bar

When multiple orders could trigger on the same bar:

1. **Stop entries** evaluated first (lower layer first: entry1 before entry2).
2. **Limit exits** evaluated after entries.
3. Only ONE entry can fill per bar per entry ID.
4. If an entry and exit both trigger on the same bar, the entry fills first, then exit is evaluated against updated position.

**Justification**: Pine Script processes entries before exits within a bar when `calc_on_order_fills = false`.

### 2.3 Metrics to Compute

#### 2.3.1 Per-Symbol Metrics

| Metric | Definition |
|--------|-----------|
| **Net Profit** | `final_equity - initial_capital` (USDT and %) |
| **Net Profit (%)** | `(final_equity - initial_capital) / initial_capital * 100` |
| **Max Drawdown** | `max over all bars of (peak_equity - current_equity) / peak_equity * 100` where peak_equity = running max of equity curve |
| **Max Drawdown Duration** | Longest period (in bars and calendar time) between equity peak and recovery to new peak |
| **Profit Factor** | `sum(gross_profits) / abs(sum(gross_losses))` where profit/loss is per round-trip trade |
| **Win Rate** | `count(trades where net_pnl > 0) / count(all_trades)` — a "trade" is a full round-trip (all DCA layers entry to all exits) |
| **Average Trade** | `net_profit / total_trades` (USDT) |
| **Average Trade (%)** | Mean of per-trade percentage returns |
| **Exposure** | `bars_in_position / total_bars * 100` |
| **Avg Time in Trade** | `mean(exit_bar - entry_bar) * 30 minutes` per round-trip |
| **Total Trades** | Count of complete round-trips |
| **Max Consecutive Wins** | Longest streak of profitable trades |
| **Max Consecutive Losses** | Longest streak of losing trades |
| **Expectancy** | `win_rate * avg_win - (1 - win_rate) * avg_loss` |
| **Sharpe Ratio (30m)** | `mean(bar_returns) / std(bar_returns) * sqrt(17520)` (17520 = 30m bars per year) |

#### 2.3.2 Daily PnL Distribution (per symbol)

```
daily_pnl[d] = equity_at_end_of_day[d] - equity_at_start_of_day[d]
daily_pnl_pct[d] = daily_pnl[d] / equity_at_start_of_day[d] * 100
```

Report: mean, std, min (worst day), max (best day), skewness, kurtosis, percentiles [1%, 5%, 25%, 50%, 75%, 95%, 99%].

**Worst Day**: `min(daily_pnl_pct)` — the most negative daily return.

#### 2.3.3 Max Single Position Loss

Two definitions provided:

1. **Trade-level return** (default): For a completed round-trip, `(total_exit_proceeds - total_entry_cost - commissions) / total_entry_cost * 100`. Report `min(trade_returns)`.

2. **Peak-to-trough within a trade**: While a position is open, track `mark_to_market_equity = unrealized_pnl + realized_exits_so_far - commissions`. Report `max over all trades of (peak_mtm - trough_mtm) / entry_cost * 100`.

**Default**: Report BOTH. Use trade-level return as the headline "Max Single Position Loss."

#### 2.3.4 Portfolio-Level Metrics

Same metrics as per-symbol, computed on the aggregated equity curve:
```
portfolio_equity[bar] = sum over all symbols of symbol_equity[bar]
```

Additional portfolio metrics:
- **Correlation matrix**: pairwise correlation of daily symbol PnLs.
- **Diversification ratio**: `sum(symbol_volatilities * weights) / portfolio_volatility`.
- **Worst symbol**: symbol with lowest net profit.
- **Best symbol**: symbol with highest net profit.

### 2.4 Robustness Checks

#### 2.4.1 Parameter Sensitivity

Sweep each parameter independently while holding others at defaults:

| Parameter | Range | Step |
|-----------|-------|------|
| lowestBars | 3, 5, 7, 10, 14 | — |
| layer2ThresholdPercent | 2, 3, 4, 5, 7 | — |
| layer3ThresholdPercent | 6, 8, 10, 12, 15 | — |
| layer4ThresholdPercent | 15, 18, 22, 25, 30 | — |
| positionsSizeMultiplier | 1.0, 1.5, 2.0, 2.5, 3.0 | — |
| takeprofitNumAtr | 1.0, 1.5, 2.0, 2.5, 3.0, 4.0 | — |
| enable_AO | true, false | — |
| enable_MFI | true, false | — |

**Total combinations for full grid**: 5 * 5 * 5 * 5 * 5 * 6 * 2 * 2 = 150,000. Too many for full grid.

**Recommended approach**:
1. **One-at-a-time**: Sweep each parameter while others are at defaults. 5+5+5+5+5+6+2+2 = 35 runs per symbol.
2. **Key interactions**: Sweep (layer2%, layer3%, layer4%) together (125 combos) and (mult, atrMult) together (30 combos). ~155 runs per symbol.
3. **Random search** (optional): 500 random parameter combinations sampled uniformly from ranges.

**Output**: Heatmaps of net_profit, max_drawdown, profit_factor for each parameter pair.

#### 2.4.2 Out-of-Sample Split

```
Total period: 2024-01-01 to 2026-01-01 (2 years of 30m data)
In-sample:    2024-01-01 to 2025-06-30 (18 months, ~26,280 bars)
Out-of-sample: 2025-07-01 to 2026-01-01 (6 months, ~8,760 bars)
```

**Validation criteria**: A parameter set is "valid" if:
- OOS net profit > 0
- OOS max drawdown < 2 * IS max drawdown
- OOS profit factor > 1.0
- OOS win rate within ±15% of IS win rate

#### 2.4.3 Walk-Forward Analysis

```
Window: 6-month training, 2-month testing, 2-month step
Step 1: Train 2024-01 to 2024-06, Test 2024-07 to 2024-08
Step 2: Train 2024-03 to 2024-08, Test 2024-09 to 2024-10
Step 3: Train 2024-05 to 2024-10, Test 2024-11 to 2024-12
Step 4: Train 2024-07 to 2024-12, Test 2025-01 to 2025-02
Step 5: Train 2024-09 to 2025-02, Test 2025-03 to 2025-04
Step 6: Train 2024-11 to 2025-04, Test 2025-05 to 2025-06
Step 7: Train 2025-01 to 2025-06, Test 2025-07 to 2025-08
Step 8: Train 2025-03 to 2025-08, Test 2025-09 to 2025-10
Step 9: Train 2025-05 to 2025-10, Test 2025-11 to 2025-12
```

For each step: optimize parameters on training window, apply best params on test window. Concatenate all test-window equity curves. Report **Walk-Forward Efficiency** = `OOS_annual_return / IS_annual_return`.

Accept if WFE > 0.5 (OOS retains at least 50% of IS performance).

---

## 3) Monitoring System (Live / Paper)

### 3.1 Per-Bar Log Record

Every 30-minute bar, emit one record per active symbol:

```json
{
  "log_type": "bar",
  "timestamp_utc": "2025-06-15T14:30:00Z",
  "symbol": "BTCUSDT",
  "timeframe": "30m",

  "ohlcv": {
    "open": 65432.10,
    "high": 65890.00,
    "low": 65100.50,
    "close": 65780.20,
    "volume": 1234.56
  },

  "indicators": {
    "hl2": 65495.25,
    "smma_13": 64800.00,
    "smma_8": 65100.00,
    "smma_5": 65300.00,
    "jaw": 63900.00,
    "teeth": 64500.00,
    "lips": 64900.00,
    "atr_14": 450.30,
    "ao": -120.50,
    "ao_diff": -15.30,
    "mfi": 8500000.00,
    "pre_mfi": 9200000.00,
    "squatbar": false,
    "squatbar_1": true,
    "squatbar_2": false,
    "is_lowest_bar": true,
    "is_bullish_reversal_bar": true,
    "is_true_bullish_reversal_bar": false
  },

  "signal_state": {
    "bull_bar_confirmation_level": 65890.00,
    "bull_bar_invalidation_level": 65100.50,
    "confirmation_level_is_nan": false,
    "invalidation_level_is_nan": false
  },

  "position_state": {
    "current_layer": 1,
    "open_trades": 1,
    "layer1_price": 65890.00,
    "layer2_threshold": 63254.40,
    "layer3_threshold": 59301.00,
    "layer4_threshold": 51394.20,
    "position_avg_price": 65890.00,
    "position_qty": 0.01013,
    "position_unrealized_pnl": -1.11,
    "take_profit_level": 66790.60
  },

  "equity_state": {
    "equity": 9998.89,
    "cash": 9331.89,
    "open_position_value": 667.00,
    "daily_realized_pnl": 0.00,
    "daily_unrealized_pnl": -1.11,
    "daily_total_pnl": -1.11,
    "day_start_equity": 10000.00
  },

  "risk_state": {
    "symbol_disabled": false,
    "disable_reason": null,
    "disable_until": null,
    "daily_loss_pct": -0.011,
    "rolling_14d_drawdown_pct": -0.011,
    "consecutive_losses": 0,
    "atr_spike_percentile": 45
  },

  "pending_orders": [
    {
      "id": "entry1",
      "type": "buy_stop",
      "price": 65890.00,
      "qty": 0.01013,
      "status": "filled"
    }
  ]
}
```

### 3.1.1 Per-Fill Log Record

On every order fill, emit:

```json
{
  "log_type": "fill",
  "timestamp_utc": "2025-06-15T14:30:00Z",
  "symbol": "BTCUSDT",
  "order_id": "entry1",
  "direction": "long",
  "order_type": "buy_stop",
  "trigger_price": 65890.00,
  "fill_price": 65890.05,
  "qty": 0.01013,
  "notional_value": 667.45,
  "commission": 0.67,
  "slippage_cost": 0.0005,
  "layer": 1,
  "position_avg_price_after": 65890.05,
  "position_qty_after": 0.01013,
  "equity_after": 9999.33,
  "take_profit_after": 66790.65,
  "bar_ohlcv": { "open": 65432.10, "high": 65890.00, "low": 65100.50, "close": 65780.20, "volume": 1234.56 }
}
```

### 3.2 Trade Journal Schema

#### 3.2.1 SQL Schema

```sql
-- Symbols table
CREATE TABLE symbols (
    symbol_id       SERIAL PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL UNIQUE,  -- e.g. 'BTCUSDT'
    tick_size       DECIMAL(18,8) NOT NULL,
    min_qty         DECIMAL(18,8) NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    disabled_until  TIMESTAMP NULL,
    disable_reason  VARCHAR(100) NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Round-trip trades (one per full position cycle: all entries to all exits)
CREATE TABLE trades (
    trade_id        SERIAL PRIMARY KEY,
    symbol_id       INT REFERENCES symbols(symbol_id),
    status          VARCHAR(10) NOT NULL,          -- 'open', 'closed', 'force_closed'
    max_layers      INT NOT NULL DEFAULT 0,        -- 1..4, how many DCA layers were used

    -- First entry
    entry1_time     TIMESTAMP NULL,
    entry1_price    DECIMAL(18,8) NULL,
    entry1_qty      DECIMAL(18,8) NULL,
    entry1_commission DECIMAL(18,8) NULL,

    -- DCA entries
    entry2_time     TIMESTAMP NULL,
    entry2_price    DECIMAL(18,8) NULL,
    entry2_qty      DECIMAL(18,8) NULL,
    entry2_commission DECIMAL(18,8) NULL,

    entry3_time     TIMESTAMP NULL,
    entry3_price    DECIMAL(18,8) NULL,
    entry3_qty      DECIMAL(18,8) NULL,
    entry3_commission DECIMAL(18,8) NULL,

    entry4_time     TIMESTAMP NULL,
    entry4_price    DECIMAL(18,8) NULL,
    entry4_qty      DECIMAL(18,8) NULL,
    entry4_commission DECIMAL(18,8) NULL,

    -- Aggregated position
    total_qty       DECIMAL(18,8) NOT NULL DEFAULT 0,
    avg_entry_price DECIMAL(18,8) NULL,
    total_entry_cost DECIMAL(18,8) NULL,           -- sum(qty * price) across all entries
    total_entry_commission DECIMAL(18,8) NULL,

    -- Exit
    exit_time       TIMESTAMP NULL,
    exit_price      DECIMAL(18,8) NULL,
    exit_commission DECIMAL(18,8) NULL,

    -- PnL
    gross_pnl       DECIMAL(18,8) NULL,            -- (exit_price - avg_entry) * total_qty
    net_pnl         DECIMAL(18,8) NULL,            -- gross_pnl - all_commissions
    net_pnl_pct     DECIMAL(8,4) NULL,             -- net_pnl / total_entry_cost * 100

    -- Timing
    duration_bars   INT NULL,                      -- exit_bar_index - entry1_bar_index
    duration_hours  DECIMAL(10,2) NULL,

    -- Peak-to-trough tracking
    max_unrealized_pnl   DECIMAL(18,8) NULL,       -- best mark-to-market during trade
    min_unrealized_pnl   DECIMAL(18,8) NULL,       -- worst mark-to-market during trade
    max_drawdown_in_trade DECIMAL(8,4) NULL,        -- (peak_mtm - trough_mtm) / entry_cost %

    -- Quality scores (computed post-trade)
    setup_quality_score  DECIMAL(5,2) NULL,         -- 0..100
    trade_quality_score  DECIMAL(5,2) NULL,         -- 0..100

    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- Bar-level log (append-only, high volume)
CREATE TABLE bar_logs (
    id              BIGSERIAL PRIMARY KEY,
    symbol_id       INT REFERENCES symbols(symbol_id),
    timestamp_utc   TIMESTAMP NOT NULL,
    open            DECIMAL(18,8),
    high            DECIMAL(18,8),
    low             DECIMAL(18,8),
    close           DECIMAL(18,8),
    volume          DECIMAL(18,8),
    jaw             DECIMAL(18,8),
    teeth           DECIMAL(18,8),
    lips            DECIMAL(18,8),
    atr_14          DECIMAL(18,8),
    ao              DECIMAL(18,8),
    ao_diff         DECIMAL(18,8),
    squatbar        BOOLEAN,
    is_true_bull_reversal BOOLEAN,
    confirmation_level DECIMAL(18,8),
    invalidation_level DECIMAL(18,8),
    current_layer   INT,
    take_profit_level DECIMAL(18,8),
    equity          DECIMAL(18,8),
    daily_pnl_pct   DECIMAL(8,4),
    symbol_disabled BOOLEAN DEFAULT FALSE
);
CREATE INDEX idx_bar_logs_symbol_ts ON bar_logs(symbol_id, timestamp_utc);

-- Fill log
CREATE TABLE fills (
    fill_id         BIGSERIAL PRIMARY KEY,
    trade_id        INT REFERENCES trades(trade_id),
    symbol_id       INT REFERENCES symbols(symbol_id),
    timestamp_utc   TIMESTAMP NOT NULL,
    order_id        VARCHAR(20) NOT NULL,          -- 'entry1'..'entry4' or 'exit1'..'exit4'
    side            VARCHAR(4) NOT NULL,           -- 'buy' or 'sell'
    fill_price      DECIMAL(18,8) NOT NULL,
    qty             DECIMAL(18,8) NOT NULL,
    commission      DECIMAL(18,8) NOT NULL,
    layer           INT NOT NULL
);

-- Daily PnL summary per symbol
CREATE TABLE daily_pnl (
    id              SERIAL PRIMARY KEY,
    symbol_id       INT REFERENCES symbols(symbol_id),
    date_utc        DATE NOT NULL,
    day_start_equity DECIMAL(18,8) NOT NULL,
    realized_pnl    DECIMAL(18,8) NOT NULL DEFAULT 0,
    unrealized_pnl  DECIMAL(18,8) NOT NULL DEFAULT 0,
    total_pnl       DECIMAL(18,8) NOT NULL DEFAULT 0,
    total_pnl_pct   DECIMAL(8,4) NOT NULL DEFAULT 0,
    num_trades_opened INT DEFAULT 0,
    num_trades_closed INT DEFAULT 0,
    symbol_disabled BOOLEAN DEFAULT FALSE,
    UNIQUE(symbol_id, date_utc)
);

-- Kill-switch event log
CREATE TABLE kill_switch_events (
    event_id        SERIAL PRIMARY KEY,
    symbol_id       INT REFERENCES symbols(symbol_id),
    event_type      VARCHAR(20) NOT NULL,          -- 'disable' or 'enable'
    trigger_rule    VARCHAR(50) NOT NULL,           -- e.g. 'daily_loss_10pct'
    trigger_value   DECIMAL(18,8),
    threshold       DECIMAL(18,8),
    disabled_until  TIMESTAMP NULL,
    notes           TEXT NULL,
    timestamp_utc   TIMESTAMP DEFAULT NOW()
);
```

### 3.3 Live Dashboards / KPIs

#### 3.3.1 Symbol Health Score (real-time, per symbol)

A composite 0–100 score updated every bar:

```
symbol_health = w1 * expectancy_score
             + w2 * drawdown_score
             + w3 * liquidity_score
             + w4 * activity_score
             + w5 * risk_flag_penalty

where:
    w1 = 0.30, w2 = 0.25, w3 = 0.15, w4 = 0.10, w5 = 0.20

    expectancy_score = clip(0, 100, 50 + rolling_30d_expectancy_pct * 10)
    drawdown_score   = clip(0, 100, 100 - rolling_14d_max_dd_pct * 5)
    liquidity_score  = clip(0, 100, min(100, median_daily_dollar_volume / 1_000_000 * 10))
    activity_score   = clip(0, 100, min(100, trades_last_30d / 5 * 100))
    risk_flag_penalty = -25 per active risk flag (daily_loss, dd, consec_loss, etc.)
                        clamped so total >= 0
```

**Display**: Color-coded gauge per symbol. Green >=70, Yellow 40-69, Red <40.

#### 3.3.2 Strategy Health Score (portfolio-level)

```
strategy_health = w1 * portfolio_expectancy_norm
                + w2 * portfolio_dd_norm
                + w3 * symbol_breadth
                + w4 * wfe_proxy

where:
    w1 = 0.30, w2 = 0.30, w3 = 0.20, w4 = 0.20

    portfolio_expectancy_norm = clip(0, 100, 50 + rolling_30d_portfolio_expectancy * 10)
    portfolio_dd_norm         = clip(0, 100, 100 - current_dd_from_peak_pct * 3)
    symbol_breadth            = (symbols_with_positive_30d_pnl / total_active_symbols) * 100
    wfe_proxy                 = clip(0, 100, recent_30d_return / best_historical_30d_return * 100)
```

#### 3.3.3 Risk Flags Dashboard

| Flag | Condition | Severity |
|------|-----------|----------|
| `DAILY_LOSS_WARNING` | dailyPnL_pct <= -5% (half of disable threshold) | WARN |
| `DAILY_LOSS_CRITICAL` | dailyPnL_pct <= -10% → symbol disabled | CRITICAL |
| `DRAWDOWN_WARNING` | 14-day rolling DD > 10% | WARN |
| `DRAWDOWN_CRITICAL` | 14-day rolling DD > 15% → symbol disabled | CRITICAL |
| `CONSEC_LOSS_WARNING` | 3 consecutive losing trades | WARN |
| `CONSEC_LOSS_CRITICAL` | 5 consecutive losing trades → symbol disabled | CRITICAL |
| `LIQUIDITY_LOW` | 7-day median dollar volume < threshold | WARN |
| `ATR_SPIKE` | ATR/close > 95th percentile of 90-day window | WARN |
| `DCA_STRESS` | 3+ round-trips hitting layer 4 in last 14 days | WARN |
| `SYMBOL_DISABLED` | Symbol is currently disabled | INFO |

---

## 4) Rating / Ranking

### 4.1 Symbol Score [0..100]

Computed daily at UTC 00:00 for each symbol with at least 1 completed trade.

#### 4.1.1 Components

**Component 1: Recent Expectancy (E_score, 35%)**

```
window = last 30 calendar days
trades_in_window = all completed round-trips with exit_time in window
N = count(trades_in_window)

if N == 0:
    E_raw = 0
else:
    win_rate = count(pnl > 0) / N
    avg_win  = mean(pnl where pnl > 0)    # USDT
    avg_loss = abs(mean(pnl where pnl <= 0))  # USDT, positive
    if avg_loss == 0:
        expectancy_ratio = 10.0  # cap
    else:
        expectancy_ratio = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_loss

    E_raw = clip(-5, 5, expectancy_ratio)

E_score = (E_raw + 5) / 10 * 100    # maps [-5, 5] → [0, 100]
```

**Component 2: Stability (S_score, 25%)**

```
rolling_14d_max_dd = max drawdown % over last 14 calendar days on this symbol's equity curve
daily_pnl_std     = std(daily_pnl_pct) over last 30 days

dd_score  = clip(0, 100, 100 - rolling_14d_max_dd * 5)
var_score = clip(0, 100, 100 - daily_pnl_std * 20)

S_score = 0.6 * dd_score + 0.4 * var_score
```

**Component 3: Liquidity Proxy (L_score, 15%)**

```
median_dollar_vol = median(daily_volume_usdt) over last 30 days
# daily_volume_usdt = sum over 48 bars of (close * volume)

L_raw = log10(max(1, median_dollar_vol))    # e.g., log10(1M) = 6

# Scale: log10(100K)=5 → score 50, log10(10M)=7 → score 100
L_score = clip(0, 100, (L_raw - 4) / 3 * 100)
```

**Component 4: Sample Size Penalty (P_score, 25%)**

```
N = number of completed trades in last 60 days
min_trades_for_full_score = 20

P_score = min(100, N / min_trades_for_full_score * 100)
```

If N < 5: force P_score = 0 (insufficient data, do not trust any score).

#### 4.1.2 Composite Score

```
symbol_score = 0.35 * E_score + 0.25 * S_score + 0.15 * L_score + 0.25 * P_score
```

**Score brackets**:
- **[80, 100]**: Top tier — full allocation.
- **[60, 80)**: Acceptable — standard allocation.
- **[40, 60)**: Cautionary — reduce allocation to 50%.
- **[20, 40)**: Poor — reduce allocation to 25%.
- **[0, 20)**: Dangerous — disable or minimum allocation.

### 4.2 Trade Quality Scores

#### 4.2.1 Setup Quality Score (at entry time, 0–100)

Computed when a new round-trip begins (layer 1 entry signal detected). Uses only information available AT the signal bar.

```
# 1. Reversal bar strength: how far above midpoint did it close?
close_vs_hl2_margin = (close - hl2) / (high - low)    # range: (0, 0.5]
reversal_strength = clip(0, 100, close_vs_hl2_margin / 0.3 * 100)

# 2. Distance below Alligator: how deep below all three lines?
min_alligator = min(jaw, teeth, lips)
distance_below_pct = (min_alligator - high) / min_alligator * 100    # positive when high < min_alligator
depth_score = clip(0, 100, distance_below_pct / 5 * 100)

# 3. Squatbar presence (0 or 1, boosted if current bar is squat)
squat_score = 0
if squatbar[0]: squat_score = 100
elif squatbar[1]: squat_score = 70
elif squatbar[2]: squat_score = 40

# 4. AO momentum (diff magnitude)
ao_diff_normalized = abs(diff) / atr    # normalize by ATR for cross-asset comparability
ao_score = clip(0, 100, ao_diff_normalized / 0.5 * 100)

# 5. Lowest bar lookback position
# How many bars since the previous low that was lower? (deeper local low = better)
bars_since_lower_low = min(lowestBars, bars since a bar had low < current low)
lookback_score = clip(0, 100, bars_since_lower_low / lowestBars * 100)

# Composite
setup_quality = (0.25 * reversal_strength
               + 0.25 * depth_score
               + 0.15 * squat_score
               + 0.20 * ao_score
               + 0.15 * lookback_score)
```

**If enable_AO = false**: ao_score weight (0.20) redistributed equally to reversal_strength and depth_score → (0.35, 0.35, 0.15, 0, 0.15).

**If enable_MFI = false**: squat_score weight (0.15) redistributed equally to reversal_strength and depth_score → same redistribution pattern.

#### 4.2.2 Trade Quality Score (post-trade, 0–100)

Computed after round-trip closes.

```
# 1. Return quality: net PnL relative to expectation
# "expected" return = historical avg trade return for this symbol
return_vs_expected = net_pnl_pct / max(0.1, symbol_avg_trade_pct)
return_score = clip(0, 100, return_vs_expected * 50)

# 2. Efficiency: how much of the available range was captured?
max_favorable_excursion = (highest high during trade - avg_entry_price) / avg_entry_price * 100
capture_ratio = net_pnl_pct / max(0.01, max_favorable_excursion)
efficiency_score = clip(0, 100, capture_ratio * 100)

# 3. Adverse excursion: how deep did it go against before profit?
max_adverse_excursion = (avg_entry_price - lowest low during trade) / avg_entry_price * 100
adversity_score = clip(0, 100, 100 - max_adverse_excursion * 5)

# 4. DCA depth: fewer layers = cleaner trade
layer_score = {1: 100, 2: 75, 3: 50, 4: 25}[max_layers]

# 5. Duration efficiency: shorter (relative to avg) = better
duration_ratio = duration_hours / max(1, symbol_avg_duration_hours)
duration_score = clip(0, 100, 100 - (duration_ratio - 1) * 50)

# Composite
trade_quality = (0.30 * return_score
               + 0.20 * efficiency_score
               + 0.20 * adversity_score
               + 0.15 * layer_score
               + 0.15 * duration_score)
```

---

## 5) Bounding / Kill-Switch Rules

### 5.1 Daily Loss Stop Per Symbol

#### 5.1.1 Core Rule

```
RULE: If daily_pnl_pct(symbol, date) <= -10.0%, then DISABLE symbol for 3 calendar days.
```

#### 5.1.2 Definitions

**Day boundary**: UTC calendar day, 00:00:00.000 to 23:59:59.999.

**Day-start equity for symbol S**:
```
day_start_equity[S, d] = allocated_capital[S, d]
    where allocated_capital = portfolio_equity_at_UTC_midnight / N_active_symbols
```
For the first day, this equals `initial_capital / N_symbols`.

**Daily PnL — Option A: Realized Only (DEFAULT)**:
```
daily_realized_pnl[S, d] = sum of net_pnl for all round-trips on symbol S
                            where exit_time falls within day d

daily_pnl_pct[S, d] = daily_realized_pnl[S, d] / day_start_equity[S, d] * 100
```

**Daily PnL — Option B: Realized + Unrealized (ALTERNATIVE)**:
```
daily_total_pnl[S, d] = daily_realized_pnl[S, d]
                       + (mark_to_market_value_end_of_day - mark_to_market_value_start_of_day)
                       for any open position on symbol S

where:
    mark_to_market_value = position_qty * last_close_of_day
    mark_to_market_value_start = position_qty_at_day_start * first_open_of_day

daily_pnl_pct[S, d] = daily_total_pnl[S, d] / day_start_equity[S, d] * 100
```

**Default choice: Option A (realized only).**

Justification: Realized PnL is unambiguous, not affected by mark-to-market noise, and avoids disabling symbols due to intraday unrealized dips that recover. Option B is more conservative but may cause excessive false positives during DCA drawdowns (where unrealized loss is expected and part of the strategy design).

**Implementation note for Option B**: If the user prefers Option B, open DCA positions with 4 layers near layer4 threshold can show ~22% unrealized drawdown by design. To avoid false disables, Option B threshold should be higher (e.g., -15% or -20%) or should only count unrealized PnL for positions with max_layers < 3.

#### 5.1.3 Disable Mechanics

```python
def check_daily_loss_stop(symbol, date, daily_pnl_pct):
    THRESHOLD = -10.0  # percent
    COOLDOWN_DAYS = 3

    if daily_pnl_pct <= THRESHOLD:
        disable_until = date + timedelta(days=COOLDOWN_DAYS)
        symbol.is_active = False
        symbol.disabled_until = disable_until
        symbol.disable_reason = f"daily_loss_{daily_pnl_pct:.2f}pct"
        log_kill_switch_event(symbol, 'disable', 'daily_loss_10pct',
                              daily_pnl_pct, THRESHOLD, disable_until)

        # IMMEDIATE ACTIONS:
        # 1. Cancel all pending entry orders for this symbol
        # 2. Do NOT force-close existing positions (they have TP orders)
        # 3. Prevent any NEW entry orders
        cancel_pending_entries(symbol)
```

**Why cooldown = 3 days**: A 10% daily loss implies abnormal conditions (crash, extreme volatility). 3 days (144 candles at 30m) allows volatility to normalize while not being so long that recovery opportunities are missed entirely.

**Why no force-close**: Existing positions have take-profit exits. Force-closing during a crash would lock in losses that the DCA structure is designed to recover from. The disable only prevents NEW entries.

#### 5.1.4 Evaluation Timing

Check runs at **every bar** (not just day boundary), comparing accumulated daily PnL so far:

```python
# On each bar during day d:
daily_realized_so_far = sum(net_pnl for exits today on this symbol)
daily_pnl_pct_so_far = daily_realized_so_far / day_start_equity * 100

if daily_pnl_pct_so_far <= -10.0:
    disable(symbol)
```

This is an **intraday check** — the symbol is disabled as soon as the threshold is breached, not at end-of-day.

---

### 5.2 Additional Bounds

#### 5.2.1 Bound #2: Rolling 14-Day Maximum Drawdown

```
RULE: If rolling_14d_max_dd(symbol) > 15%, DISABLE symbol for 5 calendar days.
```

**Definition**:
```
equity_curve_14d[S] = equity values for symbol S over the last 14 calendar days (672 bars at 30m)
peak_14d = running max of equity_curve_14d
drawdown_14d = (peak_14d - current_equity) / peak_14d * 100
rolling_14d_max_dd = max(drawdown_14d) over the window
```

**Evaluation**: Every bar. Disable immediately when threshold breached.

```python
def check_rolling_drawdown(symbol, equity_history_14d):
    THRESHOLD = 15.0  # percent
    COOLDOWN_DAYS = 5

    peak = running_max(equity_history_14d)
    dd_series = (peak - equity_history_14d) / peak * 100
    max_dd = max(dd_series)

    if max_dd > THRESHOLD:
        disable(symbol, COOLDOWN_DAYS, f"rolling_14d_dd_{max_dd:.2f}pct")
```

**Why 15%**: The strategy's max single position loss in description.txt was ~6.56%. A 15% drawdown over 14 days indicates sustained underperformance beyond normal DCA drawdowns.

#### 5.2.2 Bound #3: Consecutive Losing Trades Cap

```
RULE: If a symbol has 5 consecutive losing round-trips, DISABLE for 3 calendar days.
```

**Definition**:
```
A "losing trade" = net_pnl < 0 for a completed round-trip.
Count the streak of most recent consecutive losses.
```

```python
def check_consecutive_losses(symbol, recent_trades):
    MAX_CONSEC_LOSSES = 5
    COOLDOWN_DAYS = 3

    streak = 0
    for trade in reversed(recent_trades):  # most recent first
        if trade.net_pnl < 0:
            streak += 1
        else:
            break

    if streak >= MAX_CONSEC_LOSSES:
        disable(symbol, COOLDOWN_DAYS, f"consec_losses_{streak}")
```

**Why 5**: With a claimed 82.6% win rate, the probability of 5 consecutive losses is ~0.82^5_complement = (1-0.826)^5 ≈ 0.174^5 ≈ 0.015% — extremely rare under normal conditions. If it happens, something has changed structurally.

#### 5.2.3 Bound #4: ATR Spike Regime Filter

```
RULE: If ATR/close > 95th percentile of the trailing 90-day ATR/close distribution,
      prevent NEW entry orders (but do not disable — existing positions keep their TP).
```

**Definition**:
```
atr_pct = atr_14 / close * 100
atr_pct_history = last 90 days of atr_pct values (4320 bars at 30m)
p95 = percentile(atr_pct_history, 95)

if atr_pct > p95:
    suppress_new_entries(symbol)  # soft disable: no new trades, existing OK
```

This is a **soft bound** — it doesn't disable the symbol or cancel pending orders. It only prevents the entry logic from firing. Re-enables automatically when ATR/close drops below the 95th percentile.

```python
def check_atr_spike(symbol, atr_14, close, atr_pct_history_90d):
    current_atr_pct = atr_14 / close * 100
    p95 = np.percentile(atr_pct_history_90d, 95)

    if current_atr_pct > p95:
        symbol.entry_suppressed = True
        symbol.suppress_reason = f"atr_spike_{current_atr_pct:.2f}pct_vs_p95_{p95:.2f}pct"
    else:
        symbol.entry_suppressed = False
```

**Why 95th percentile**: Captures extreme volatility regimes (flash crashes, black swan events) where the strategy's mean-reversion assumption breaks down. Using percentile rather than absolute threshold makes it adaptive across different assets.

#### 5.2.4 Bound #5: DCA Stress Cap (Falling Knife Detector)

```
RULE: If symbol has 3 or more round-trips reaching layer 4 in the last 14 calendar days,
      DISABLE for 5 calendar days.
```

**Definition**:
```python
def check_dca_stress(symbol, recent_trades_14d):
    MAX_LAYER4_TRIPS = 3
    COOLDOWN_DAYS = 5

    layer4_count = sum(1 for t in recent_trades_14d if t.max_layers == 4)

    if layer4_count >= MAX_LAYER4_TRIPS:
        disable(symbol, COOLDOWN_DAYS, f"dca_stress_{layer4_count}_layer4_trips")
```

**Why this matters**: Repeated deployment of all 4 DCA layers means the asset keeps falling through all threshold levels. This is characteristic of a strong downtrend where the mean-reversion assumption fails. The strategy is "catching falling knives" and deploying maximum capital repeatedly.

---

### 5.3 Re-Enable Conditions

A disabled symbol can be re-enabled when ALL of the following are met:

#### 5.3.1 Condition 1: Cooldown Expiry

```
current_date >= symbol.disabled_until
```

The minimum cooldown periods are defined per bound:

| Bound | Cooldown |
|-------|----------|
| Daily loss 10% | 3 days |
| Rolling 14d DD > 15% | 5 days |
| Consecutive losses >= 5 | 3 days |
| DCA stress (3+ layer4 in 14d) | 5 days |

If multiple bounds triggered simultaneously, use the **longest** remaining cooldown.

#### 5.3.2 Condition 2: Recovery Evidence

After cooldown expires, check:

```
rolling_7d_expectancy > 0
```

Where:
```
rolling_7d_expectancy = computed on the last 7 days of "paper" signals.
    Even while disabled, the system continues to COMPUTE (but not execute)
    signals and hypothetical trade outcomes for the symbol.
    This "shadow mode" provides the data for recovery assessment.
```

If shadow-mode signals show positive expectancy over the cooldown period, the recovery condition is met.

**If no shadow trades occurred during cooldown** (possible if conditions are truly terrible): The symbol may re-enable on cooldown expiry alone, but with reduced allocation (50% of normal) for the first 7 days.

#### 5.3.3 Condition 3: Minimum Sample Size

```
shadow_trades_in_cooldown >= 3
```

At least 3 hypothetical trades must have been computed during the shadow period to provide any statistical basis for the recovery assessment.

If fewer than 3 shadow trades: extend cooldown by 3 additional days and re-check.

#### 5.3.4 Re-Enable State Machine

```
States: ACTIVE → DISABLED → COOLDOWN_COMPLETE → SHADOW_CHECK → RE_ENABLED

Transitions:
    ACTIVE → DISABLED:
        Any kill-switch triggers (5.1, 5.2.1-5.2.4)

    DISABLED → COOLDOWN_COMPLETE:
        current_date >= disabled_until

    COOLDOWN_COMPLETE → SHADOW_CHECK:
        Automatic; check shadow-mode results

    SHADOW_CHECK → RE_ENABLED:
        shadow_trades >= 3 AND rolling_7d_shadow_expectancy > 0

    SHADOW_CHECK → DISABLED (extended):
        shadow_trades < 3 → extend cooldown by 3 days
        OR shadow_expectancy <= 0 → extend cooldown by 3 days

    RE_ENABLED → ACTIVE:
        Immediate; begin accepting entry signals
        First 7 days: allocation capped at 50% of normal
        After 7 days of no new disables: full allocation restored
```

#### 5.3.5 ATR Spike (Soft Bound) — Re-Enable

The ATR spike filter (5.2.3) is stateless. It auto-enables when `atr_pct <= p95`. No cooldown, no shadow check. It is evaluated every bar independently.

---

## 6) Implementation Blueprint

### 6.1 Suggested Module Structure

```
bdb_dca/
├── __init__.py
├── config.py                  # All parameters, defaults, bounds thresholds
├── indicators.py              # SMMA, Alligator, ATR, AO, MFI, isLowestBar
├── signals.py                 # isBullishReversalBar, isTrueBullishReversalBar
├── sizing.py                  # getLayerEquityQty, geometric weights
├── strategy.py                # Core strategy state machine (confirmation/invalidation,
│                              #   layer detection, entry/exit logic)
├── orders.py                  # Order book: pending stop/limit management, fill simulation
├── risk.py                    # Kill-switch rules, daily PnL tracking, bounds checking
├── scoring.py                 # Symbol score, setup quality, trade quality
├── backtest.py                # Bar-by-bar backtest loop
├── monitor.py                 # Live/paper monitoring loop
├── data.py                    # OHLCV fetching, caching, normalization
├── db.py                      # Database connection, ORM/raw SQL, schema migration
├── logging_config.py          # Structured logging setup
├── models.py                  # Dataclasses: Bar, Order, Fill, Trade, SymbolState
└── main.py                    # CLI entry point: backtest mode, live mode, report mode
```

### 6.2 Core Data Models (Pseudocode)

```python
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, date
from enum import Enum

class OrderType(Enum):
    BUY_STOP = "buy_stop"
    SELL_LIMIT = "sell_limit"

class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"

class SymbolStatus(Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    COOLDOWN_COMPLETE = "cooldown_complete"
    SHADOW_CHECK = "shadow_check"
    RE_ENABLED = "re_enabled"

@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class Indicators:
    hl2: float
    smma_13: float          # raw SMMA, before shift
    smma_8: float
    smma_5: float
    jaw: float              # smma_13 shifted back 8 bars
    teeth: float            # smma_8 shifted back 5 bars
    lips: float             # smma_5 shifted back 3 bars
    atr_14: float
    ao: float
    ao_diff: float
    mfi: float
    pre_mfi: float
    squatbar: bool
    squatbar_1: bool        # squatbar from 1 bar ago
    squatbar_2: bool        # squatbar from 2 bars ago
    is_lowest_bar: bool
    is_bullish_reversal_bar: bool
    is_true_bullish_reversal_bar: bool

@dataclass
class PendingOrder:
    order_id: str           # 'entry1'..'entry4' or 'exit_entry1'..'exit_entry4'
    order_type: OrderType
    price: float
    qty: float
    layer: int
    placed_bar_index: int

@dataclass
class Fill:
    order_id: str
    fill_price: float
    qty: float
    commission: float
    bar_index: int
    timestamp: datetime

@dataclass
class SymbolState:
    symbol: str
    status: SymbolStatus = SymbolStatus.ACTIVE
    disabled_until: Optional[date] = None
    disable_reason: Optional[str] = None
    entry_suppressed: bool = False      # ATR spike soft filter

    # Strategy state
    bull_bar_confirmation_level: float = float('nan')
    bull_bar_invalidation_level: float = float('nan')
    take_profit_level: float = float('nan')
    current_layer: int = 0
    layer1_price: float = float('nan')
    layer2_threshold: float = float('nan')
    layer3_threshold: float = float('nan')
    layer4_threshold: float = float('nan')

    # Position tracking
    open_entries: dict = field(default_factory=dict)  # id -> {price, qty}
    total_qty: float = 0.0
    avg_entry_price: float = float('nan')

    # Pending orders
    pending_entries: dict = field(default_factory=dict)  # id -> PendingOrder
    pending_exits: dict = field(default_factory=dict)    # id -> PendingOrder

    # Equity tracking
    equity: float = 0.0
    cash: float = 0.0
    peak_equity: float = 0.0

    # Daily PnL
    day_start_equity: float = 0.0
    daily_realized_pnl: float = 0.0

    # Risk tracking
    consecutive_losses: int = 0
    trades_history: list = field(default_factory=list)

    # Indicator history (ring buffers)
    smma_13_state: float = float('nan')
    smma_8_state: float = float('nan')
    smma_5_state: float = float('nan')
    smma_13_buffer: list = field(default_factory=list)  # last 9+ values for shift
    smma_8_buffer: list = field(default_factory=list)   # last 6+ values
    smma_5_buffer: list = field(default_factory=list)   # last 4+ values
    squatbar_buffer: list = field(default_factory=lambda: [False, False, False])
```

### 6.3 Pseudocode — indicators.py

```python
import numpy as np
from collections import deque

class IndicatorEngine:
    """Computes all indicators for one symbol, bar by bar."""

    def __init__(self, config):
        self.cfg = config
        # SMMA states (one per Alligator line)
        self.smma_13_val = float('nan')
        self.smma_8_val = float('nan')
        self.smma_5_val = float('nan')
        self.smma_13_initialized = False
        self.smma_8_initialized = False
        self.smma_5_initialized = False

        # Buffers for shifted lookback
        self.smma_13_history = deque(maxlen=16)  # need [8] lookback
        self.smma_8_history = deque(maxlen=8)    # need [5] lookback
        self.smma_5_history = deque(maxlen=6)    # need [3] lookback

        # SMA buffers for AO
        self.hl2_buffer = deque(maxlen=34)       # SMA(34) needs 34 values

        # ATR state
        self.tr_buffer = deque(maxlen=14)
        self.atr_val = float('nan')
        self.atr_initialized = False

        # Low buffer for isLowestBar
        self.low_buffer = deque(maxlen=max(config.lowest_bars, 1))

        # Squatbar history
        self.squatbar_history = deque([False, False, False], maxlen=3)

        # Previous bar data for MFI
        self.prev_high = float('nan')
        self.prev_low = float('nan')
        self.prev_volume = float('nan')

        # Previous AO for diff
        self.prev_ao = float('nan')

        # Previous bar for crossover/crossunder
        self.prev_bar_high = float('nan')
        self.prev_bar_low = float('nan')

        # Bar count
        self.bar_count = 0

    def _update_smma(self, src, length, current_val, initialized):
        """Compute one step of SMMA."""
        # We need SMA for initialization — requires `length` values
        # This is handled by checking if current_val is nan
        if np.isnan(current_val):
            # Need at least `length` bars of src history for SMA
            # Caller must track this; here we just attempt
            return float('nan'), False
        else:
            new_val = (current_val * (length - 1) + src) / length
            return new_val, True

    def compute(self, bar: Bar) -> Indicators:
        """Process one bar and return all indicator values."""
        self.bar_count += 1
        hl2 = (bar.high + bar.low) / 2.0
        self.hl2_buffer.append(hl2)

        # --- SMMA updates ---
        # SMMA(hl2, 13)
        if not self.smma_13_initialized and len(self.hl2_buffer) >= 13:
            self.smma_13_val = np.mean(list(self.hl2_buffer)[-13:])
            self.smma_13_initialized = True
        elif self.smma_13_initialized:
            self.smma_13_val = (self.smma_13_val * 12 + hl2) / 13

        # SMMA(hl2, 8)
        if not self.smma_8_initialized and len(self.hl2_buffer) >= 8:
            self.smma_8_val = np.mean(list(self.hl2_buffer)[-8:])
            self.smma_8_initialized = True
        elif self.smma_8_initialized:
            self.smma_8_val = (self.smma_8_val * 7 + hl2) / 8

        # SMMA(hl2, 5)
        if not self.smma_5_initialized and len(self.hl2_buffer) >= 5:
            self.smma_5_val = np.mean(list(self.hl2_buffer)[-5:])
            self.smma_5_initialized = True
        elif self.smma_5_initialized:
            self.smma_5_val = (self.smma_5_val * 4 + hl2) / 5

        # Store SMMA history for shifted lookback
        self.smma_13_history.append(self.smma_13_val)
        self.smma_8_history.append(self.smma_8_val)
        self.smma_5_history.append(self.smma_5_val)

        # Alligator lines (shifted = lookback into history)
        jaw = self.smma_13_history[-9] if len(self.smma_13_history) >= 9 else float('nan')
        teeth = self.smma_8_history[-6] if len(self.smma_8_history) >= 6 else float('nan')
        lips = self.smma_5_history[-4] if len(self.smma_5_history) >= 4 else float('nan')

        # --- ATR(14) ---
        if not np.isnan(self.prev_bar_high):
            tr = max(bar.high - bar.low,
                     abs(bar.high - self.prev_bar_low),   # note: prev close not available
                     abs(bar.low - self.prev_bar_low))
            # Actually need prev_close. Let's use prev_close:
            # We need to store prev_close. Fix:
            pass  # see corrected version below

        # Corrected ATR: need prev_close
        # Store self.prev_close; compute TR properly
        # TR = max(H-L, |H - prev_close|, |L - prev_close|)
        tr = float('nan')
        if hasattr(self, 'prev_close') and not np.isnan(self.prev_close):
            tr = max(bar.high - bar.low,
                     abs(bar.high - self.prev_close),
                     abs(bar.low - self.prev_close))
        else:
            tr = bar.high - bar.low  # first bar fallback

        self.tr_buffer.append(tr)
        if not self.atr_initialized and len(self.tr_buffer) >= 14:
            self.atr_val = np.mean(list(self.tr_buffer)[-14:])
            self.atr_initialized = True
        elif self.atr_initialized:
            self.atr_val = (self.atr_val * 13 + tr) / 14  # RMA/Wilder smoothing

        # --- AO ---
        ao = float('nan')
        ao_diff = float('nan')
        if len(self.hl2_buffer) >= 34:
            sma5 = np.mean(list(self.hl2_buffer)[-5:])
            sma34 = np.mean(list(self.hl2_buffer)[-34:])
            ao = sma5 - sma34
            if not np.isnan(self.prev_ao):
                ao_diff = ao - self.prev_ao

        # --- MFI ---
        mfi = float('nan')
        pre_mfi = float('nan')
        squatbar = False
        if bar.volume > 0:
            mfi = 1e9 * (bar.high - bar.low) / bar.volume
        if self.prev_volume > 0 and not np.isnan(self.prev_high):
            pre_mfi = 1e9 * (self.prev_high - self.prev_low) / self.prev_volume

        if not np.isnan(mfi) and not np.isnan(pre_mfi):
            squatbar = (mfi < pre_mfi) and (bar.volume > self.prev_volume)

        self.squatbar_history.append(squatbar)
        squatbar_0 = self.squatbar_history[-1]
        squatbar_1 = self.squatbar_history[-2] if len(self.squatbar_history) >= 2 else False
        squatbar_2 = self.squatbar_history[-3] if len(self.squatbar_history) >= 3 else False

        # --- isLowestBar ---
        self.low_buffer.append(bar.low)
        if self.cfg.lowest_bars == 0:
            is_lowest_bar = False
        elif len(self.low_buffer) >= self.cfg.lowest_bars:
            is_lowest_bar = (min(list(self.low_buffer)[-self.cfg.lowest_bars:]) == bar.low)
        else:
            is_lowest_bar = (min(self.low_buffer) == bar.low)

        # --- Base bullish reversal bar ---
        is_bullish_reversal = (bar.close > hl2) and is_lowest_bar

        # --- True bullish reversal bar ---
        below_alligator = (bar.high < jaw and bar.high < teeth and bar.high < lips)
        is_true = False

        if not np.isnan(jaw) and not np.isnan(teeth) and not np.isnan(lips):
            if self.cfg.enable_ao and self.cfg.enable_mfi:
                is_true = (is_bullish_reversal and below_alligator
                           and ao_diff < 0
                           and (squatbar_0 or squatbar_1 or squatbar_2))
            elif self.cfg.enable_ao and not self.cfg.enable_mfi:
                is_true = (is_bullish_reversal and below_alligator
                           and ao_diff < 0)
            elif not self.cfg.enable_ao and self.cfg.enable_mfi:
                is_true = (is_bullish_reversal and below_alligator
                           and (squatbar_0 or squatbar_1 or squatbar_2))
            else:
                is_true = (is_bullish_reversal and below_alligator)

        # Update prev state
        self.prev_high = bar.high
        self.prev_low = bar.low
        self.prev_volume = bar.volume
        self.prev_close = bar.close
        self.prev_ao = ao
        self.prev_bar_high = bar.high
        self.prev_bar_low = bar.low

        return Indicators(
            hl2=hl2,
            smma_13=self.smma_13_val, smma_8=self.smma_8_val, smma_5=self.smma_5_val,
            jaw=jaw, teeth=teeth, lips=lips,
            atr_14=self.atr_val,
            ao=ao, ao_diff=ao_diff,
            mfi=mfi, pre_mfi=pre_mfi,
            squatbar=squatbar_0, squatbar_1=squatbar_1, squatbar_2=squatbar_2,
            is_lowest_bar=is_lowest_bar,
            is_bullish_reversal_bar=is_bullish_reversal,
            is_true_bullish_reversal_bar=is_true
        )
```

### 6.4 Pseudocode — strategy.py (Core State Machine)

```python
import math

class StrategyEngine:
    """Manages strategy state for one symbol: levels, layers, orders, exits."""

    def __init__(self, config, initial_capital):
        self.cfg = config
        self.equity = initial_capital
        self.cash = initial_capital
        self.peak_equity = initial_capital

        # Persistent state (mirrors Pine `var` variables)
        self.bull_confirm = float('nan')    # bullBarConfirmationLevel
        self.bull_invalid = float('nan')    # bullBarInvalidationLevel
        self.tp_level = float('nan')        # takeProfitLevel
        self.current_layer = 0
        self.layer1_price = float('nan')
        self.layer2_thresh = float('nan')
        self.layer3_thresh = float('nan')
        self.layer4_thresh = float('nan')

        # Open entries: {entry_id: {price, qty}}
        self.open_entries = {}
        self.pending_stop_entries = {}    # {entry_id: PendingOrder}
        self.pending_limit_exits = {}    # {entry_id: PendingOrder}

        # Previous bar values for crossover/crossunder
        self.prev_high = float('nan')
        self.prev_low = float('nan')
        self.prev_bull_confirm = float('nan')
        self.prev_bull_invalid = float('nan')
        self.prev_opentrades = 0

    @property
    def opentrades(self):
        return len(self.open_entries)

    @property
    def position_avg_price(self):
        if not self.open_entries:
            return float('nan')
        total_cost = sum(e['price'] * e['qty'] for e in self.open_entries.values())
        total_qty = sum(e['qty'] for e in self.open_entries.values())
        return total_cost / total_qty if total_qty > 0 else float('nan')

    @property
    def total_qty(self):
        return sum(e['qty'] for e in self.open_entries.values())

    def get_layer_equity_qty(self, layer_index, price):
        """Geometric position sizing. layer_index = 0,1,2,3."""
        mult = self.cfg.position_size_multiplier
        sum_w = 1.0 + mult + mult**2 + mult**3
        w_cur = mult ** layer_index
        pct = w_cur / sum_w
        cap = self.equity * pct
        qty = cap / price if price > 0 else 0
        return qty

    def process_bar(self, bar, indicators, bar_index, in_window):
        """Process one bar: fills, signal updates, new orders. Returns list of Fill objects."""
        fills = []

        # ============================================================
        # STEP 1: Process pending order fills at bar open / intrabar
        # ============================================================

        # 1a. Stop entries (buy-stop): check if bar triggers
        for eid in list(self.pending_stop_entries.keys()):
            order = self.pending_stop_entries[eid]
            fill_price = None

            if bar.open >= order.price:
                fill_price = bar.open + self._slippage(bar.open)
            elif bar.high >= order.price:
                fill_price = order.price + self._slippage(order.price)

            if fill_price is not None:
                commission = order.qty * fill_price * self.cfg.commission_rate
                self.open_entries[eid] = {'price': fill_price, 'qty': order.qty}
                self.cash -= (order.qty * fill_price + commission)
                del self.pending_stop_entries[eid]
                fills.append(Fill(
                    order_id=eid, fill_price=fill_price, qty=order.qty,
                    commission=commission, bar_index=bar_index,
                    timestamp=bar.timestamp
                ))

        # 1b. Limit exits (sell-limit): check if bar triggers
        for eid in list(self.pending_limit_exits.keys()):
            order = self.pending_limit_exits[eid]
            if eid not in self.open_entries:
                del self.pending_limit_exits[eid]
                continue

            fill_price = None
            if bar.open >= order.price:
                fill_price = bar.open        # gap up: fill at open (favorable)
            elif bar.high >= order.price:
                fill_price = order.price     # touch: fill at limit

            if fill_price is not None:
                entry = self.open_entries[eid]
                commission = entry['qty'] * fill_price * self.cfg.commission_rate
                self.cash += (entry['qty'] * fill_price - commission)
                del self.open_entries[eid]
                del self.pending_limit_exits[eid]
                fills.append(Fill(
                    order_id=f"exit_{eid}", fill_price=fill_price,
                    qty=entry['qty'], commission=commission,
                    bar_index=bar_index, timestamp=bar.timestamp
                ))

        # ============================================================
        # STEP 2: Update equity
        # ============================================================
        mtm = sum(e['qty'] * bar.close for e in self.open_entries.values())
        self.equity = self.cash + mtm
        self.peak_equity = max(self.peak_equity, self.equity)

        # ============================================================
        # STEP 3: Signal logic (mirrors Pine execution order)
        # ============================================================

        # 3a. Set confirmation/invalidation if reversal bar
        if indicators.is_true_bullish_reversal_bar:
            self.bull_confirm = bar.high
            self.bull_invalid = bar.low

        # 3b. Check invalidation / confirmation crossover → reset levels
        cross_up = (not math.isnan(self.prev_bull_confirm)
                    and self.prev_high < self.prev_bull_confirm
                    and bar.high > self.bull_confirm)
        cross_down = (not math.isnan(self.prev_bull_invalid)
                      and self.prev_low > self.prev_bull_invalid
                      and bar.low < self.bull_invalid)

        # Note: crossover/crossunder compare (current_val vs level) AND
        # (prev_val vs prev_level). Since levels are persistent (var),
        # prev_level = current_level unless just changed this bar.
        # Simplified: crossover(high, confirm) = prev_high <= prev_confirm AND high > confirm
        # crossunder(low, invalid) = prev_low >= prev_invalid AND low < invalid

        if cross_up or cross_down:
            self.bull_confirm = float('nan')
            self.bull_invalid = float('nan')

        # 3c. Layer detection (opentrades transitions)
        curr_ot = self.opentrades
        prev_ot = self.prev_opentrades

        if curr_ot == 1 and prev_ot == 0:
            self.layer1_price = self.position_avg_price
            self.current_layer = 1
        elif curr_ot == 2 and prev_ot == 1:
            self.current_layer = 2
        elif curr_ot == 3 and prev_ot == 2:
            self.current_layer = 3
        elif curr_ot == 4 and prev_ot == 3:
            self.current_layer = 4

        # 3d. Threshold computation
        if not math.isnan(self.layer1_price):
            self.layer2_thresh = self.layer1_price * (100 - self.cfg.layer2_pct) / 100
            self.layer3_thresh = self.layer1_price * (100 - self.cfg.layer3_pct) / 100
            self.layer4_thresh = self.layer1_price * (100 - self.cfg.layer4_pct) / 100

        # 3e. Take profit computation
        if self.opentrades > 0:
            self.tp_level = self.position_avg_price + indicators.atr_14 * self.cfg.atr_mult
        else:
            self.tp_level = float('nan')

        # ============================================================
        # STEP 4: Place entry orders (if conditions met)
        # ============================================================
        is_signal = indicators.is_true_bullish_reversal_bar
        confirm_valid = not math.isnan(self.bull_confirm) and self.bull_confirm > 0

        if in_window and is_signal and confirm_valid:
            if self.current_layer == 0:
                qty = self.get_layer_equity_qty(0, self.bull_confirm)
                self.pending_stop_entries['entry1'] = PendingOrder(
                    order_id='entry1', order_type=OrderType.BUY_STOP,
                    price=self.bull_confirm, qty=qty, layer=1,
                    placed_bar_index=bar_index)

            elif self.current_layer == 1 and bar.low < self.layer2_thresh:
                qty = self.get_layer_equity_qty(1, self.bull_confirm)
                self.pending_stop_entries['entry2'] = PendingOrder(
                    order_id='entry2', order_type=OrderType.BUY_STOP,
                    price=self.bull_confirm, qty=qty, layer=2,
                    placed_bar_index=bar_index)

            elif self.current_layer == 2 and bar.low < self.layer3_thresh:
                qty = self.get_layer_equity_qty(2, self.bull_confirm)
                self.pending_stop_entries['entry3'] = PendingOrder(
                    order_id='entry3', order_type=OrderType.BUY_STOP,
                    price=self.bull_confirm, qty=qty, layer=3,
                    placed_bar_index=bar_index)

            elif self.current_layer == 3 and bar.low < self.layer4_thresh:
                qty = self.get_layer_equity_qty(3, self.bull_confirm)
                self.pending_stop_entries['entry4'] = PendingOrder(
                    order_id='entry4', order_type=OrderType.BUY_STOP,
                    price=self.bull_confirm, qty=qty, layer=4,
                    placed_bar_index=bar_index)

        # ============================================================
        # STEP 5: Place/update exit orders (every bar while position open)
        # ============================================================
        if self.opentrades > 0 and not math.isnan(self.tp_level):
            for eid in self.open_entries:
                self.pending_limit_exits[eid] = PendingOrder(
                    order_id=f"exit_{eid}", order_type=OrderType.SELL_LIMIT,
                    price=self.tp_level, qty=self.open_entries[eid]['qty'],
                    layer=0, placed_bar_index=bar_index)

        # ============================================================
        # STEP 6: End-of-bar layer reset (line 192 in Pine)
        # ============================================================
        if self.opentrades == 0:
            self.current_layer = 0

        # Save prev state for next bar
        self.prev_high = bar.high
        self.prev_low = bar.low
        self.prev_bull_confirm = self.bull_confirm
        self.prev_bull_invalid = self.bull_invalid
        self.prev_opentrades = self.opentrades

        return fills

    def _slippage(self, price):
        """Return slippage amount for a fill at given price."""
        return max(5 * self.cfg.tick_size, price * 0.0001)
```

### 6.5 Pseudocode — backtest.py (Bar-by-Bar Loop)

```python
from datetime import datetime, timezone, timedelta

class Backtester:
    def __init__(self, config, symbols, ohlcv_data):
        """
        config: global config
        symbols: list of symbol strings
        ohlcv_data: dict {symbol: list of Bar objects, sorted by timestamp}
        """
        self.cfg = config
        self.symbols = symbols
        self.data = ohlcv_data
        self.results = {}  # symbol -> BacktestResult

    def run(self):
        for symbol in self.symbols:
            result = self._run_symbol(symbol, self.data[symbol])
            self.results[symbol] = result
        return self.results

    def _run_symbol(self, symbol, bars):
        capital = self.cfg.initial_capital / len(self.symbols)
        indicator_engine = IndicatorEngine(self.cfg)
        strategy_engine = StrategyEngine(self.cfg, capital)
        risk_engine = RiskEngine(self.cfg, symbol, capital)

        trades = []         # completed round-trips
        current_trade = None
        equity_curve = []
        bar_logs = []

        for i, bar in enumerate(bars):
            # --- Day boundary check ---
            if i == 0 or bars[i].timestamp.date() != bars[i-1].timestamp.date():
                # New day: snapshot day-start equity, reset daily PnL
                risk_engine.on_new_day(strategy_engine.equity, bar.timestamp.date())

            # --- Check if symbol is disabled ---
            if risk_engine.is_disabled(bar.timestamp.date()):
                # Still compute indicators (for shadow mode) but skip strategy
                indicators = indicator_engine.compute(bar)
                risk_engine.shadow_process(bar, indicators, strategy_engine)
                equity_curve.append(strategy_engine.equity)
                continue

            # --- Check ATR spike suppression ---
            # (computed after indicators)

            # --- Compute indicators ---
            indicators = indicator_engine.compute(bar)

            # --- ATR spike check ---
            atr_suppressed = risk_engine.check_atr_spike(
                indicators.atr_14, bar.close)

            # --- Determine if in trading window ---
            in_window = (self.cfg.start_time <= bar.timestamp <= self.cfg.end_time
                         and not atr_suppressed)

            # --- Process bar through strategy ---
            fills = strategy_engine.process_bar(bar, indicators, i, in_window)

            # --- Process fills into trade records ---
            for fill in fills:
                if fill.order_id.startswith('entry'):
                    if current_trade is None:
                        current_trade = TradeRecord(symbol=symbol)
                    current_trade.add_entry(fill)
                elif fill.order_id.startswith('exit_'):
                    if current_trade is not None:
                        current_trade.add_exit(fill)

            # --- Check if round-trip completed ---
            if current_trade and strategy_engine.opentrades == 0:
                current_trade.finalize(strategy_engine.equity)
                trades.append(current_trade)

                # Update risk engine with completed trade
                risk_engine.on_trade_closed(current_trade)

                current_trade = None

            # --- Update mark-to-market for open trade ---
            if current_trade and strategy_engine.opentrades > 0:
                current_trade.update_mtm(bar, strategy_engine)

            # --- Daily PnL tracking ---
            risk_engine.update_daily_pnl(strategy_engine.equity, fills)

            # --- Kill-switch checks ---
            risk_engine.check_daily_loss(strategy_engine)
            risk_engine.check_rolling_drawdown(strategy_engine)
            risk_engine.check_consecutive_losses()
            risk_engine.check_dca_stress()

            # --- Record equity ---
            equity_curve.append(strategy_engine.equity)

            # --- Logging ---
            bar_logs.append(self._make_bar_log(
                symbol, bar, indicators, strategy_engine, risk_engine))

        # --- Force-close at end of backtest ---
        if strategy_engine.opentrades > 0 and current_trade:
            last_bar = bars[-1]
            for eid in list(strategy_engine.open_entries.keys()):
                entry = strategy_engine.open_entries[eid]
                commission = entry['qty'] * last_bar.close * self.cfg.commission_rate
                strategy_engine.cash += (entry['qty'] * last_bar.close - commission)
                current_trade.add_exit(Fill(
                    order_id=f"force_exit_{eid}", fill_price=last_bar.close,
                    qty=entry['qty'], commission=commission,
                    bar_index=len(bars)-1, timestamp=last_bar.timestamp))
            strategy_engine.open_entries.clear()
            current_trade.finalize(strategy_engine.equity)
            current_trade.status = 'force_closed'
            trades.append(current_trade)

        return BacktestResult(
            symbol=symbol,
            trades=trades,
            equity_curve=equity_curve,
            bar_logs=bar_logs,
            final_equity=strategy_engine.equity,
            initial_capital=capital
        )
```

### 6.6 Pseudocode — risk.py (Kill-Switch State Machine)

```python
from datetime import date, timedelta
from collections import deque

class RiskEngine:
    """Kill-switch and bounding logic for one symbol."""

    def __init__(self, config, symbol, initial_capital):
        self.cfg = config
        self.symbol = symbol
        self.status = SymbolStatus.ACTIVE
        self.disabled_until = None
        self.disable_reason = None
        self.re_enable_reduced_alloc_until = None

        # Daily tracking
        self.day_start_equity = initial_capital
        self.current_date = None
        self.daily_realized_pnl = 0.0

        # Rolling drawdown tracking (14-day equity buffer)
        self.equity_history_14d = deque(maxlen=672)  # 14d * 48 bars/day

        # Consecutive losses
        self.consecutive_losses = 0

        # DCA stress: track layer4 trips in last 14 days
        self.layer4_trips_14d = deque(maxlen=100)  # (date, True/False)

        # ATR spike tracking
        self.atr_pct_history_90d = deque(maxlen=4320)  # 90d * 48

        # Shadow mode
        self.shadow_trades = []

        # Event log
        self.events = []

    def is_disabled(self, current_date):
        if self.status == SymbolStatus.ACTIVE:
            return False
        if self.status == SymbolStatus.DISABLED:
            if current_date >= self.disabled_until:
                self.status = SymbolStatus.COOLDOWN_COMPLETE
                return self._check_re_enable()
            return True
        if self.status == SymbolStatus.COOLDOWN_COMPLETE:
            return self._check_re_enable()
        return False

    def _check_re_enable(self):
        """Check if re-enable conditions are met. Returns True if still disabled."""
        if len(self.shadow_trades) >= 3:
            # Check shadow expectancy
            shadow_pnls = [t.net_pnl_pct for t in self.shadow_trades[-7:]]
            if len(shadow_pnls) > 0:
                win_rate = sum(1 for p in shadow_pnls if p > 0) / len(shadow_pnls)
                avg_win = (sum(p for p in shadow_pnls if p > 0) /
                           max(1, sum(1 for p in shadow_pnls if p > 0)))
                avg_loss = abs(sum(p for p in shadow_pnls if p <= 0) /
                               max(1, sum(1 for p in shadow_pnls if p <= 0)))
                expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

                if expectancy > 0:
                    self.status = SymbolStatus.ACTIVE
                    self.shadow_trades.clear()
                    self.re_enable_reduced_alloc_until = (
                        self.current_date + timedelta(days=7))
                    self.events.append({
                        'type': 'enable', 'reason': 'recovery',
                        'shadow_expectancy': expectancy,
                        'date': self.current_date})
                    return False  # not disabled

        # Still disabled: extend cooldown by 3 days
        self.disabled_until = self.current_date + timedelta(days=3)
        return True  # still disabled

    def on_new_day(self, equity, new_date):
        self.day_start_equity = equity
        self.current_date = new_date
        self.daily_realized_pnl = 0.0

    def update_daily_pnl(self, current_equity, fills):
        """Track realized PnL from exits that happened this bar."""
        for fill in fills:
            if fill.order_id.startswith('exit_'):
                # Realized PnL for this exit = (fill_price - entry_price) * qty - commissions
                # Simplified: track total equity change due to realized exits
                pass
        # Simpler: realized PnL = exits proceeds - entry costs for trades closed today
        # But we track at trade level. So:
        self.daily_realized_pnl = current_equity - self.day_start_equity
        # Note: this mixes realized + unrealized. For pure realized, use trade records.

    def check_daily_loss(self, strategy_engine):
        """RULE 5.1: Daily loss > 10% -> disable."""
        if self.status != SymbolStatus.ACTIVE:
            return
        daily_pnl_pct = self.daily_realized_pnl / self.day_start_equity * 100
        if daily_pnl_pct <= -10.0:
            self._disable(3, f"daily_loss_{daily_pnl_pct:.2f}pct")
            # Cancel pending entries
            strategy_engine.pending_stop_entries.clear()

    def check_rolling_drawdown(self, strategy_engine):
        """RULE 5.2.1: 14-day DD > 15% -> disable."""
        if self.status != SymbolStatus.ACTIVE:
            return
        self.equity_history_14d.append(strategy_engine.equity)
        if len(self.equity_history_14d) < 48:  # need at least 1 day
            return
        eq = list(self.equity_history_14d)
        peak = eq[0]
        max_dd = 0.0
        for e in eq:
            peak = max(peak, e)
            dd = (peak - e) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)
        if max_dd > 15.0:
            self._disable(5, f"rolling_14d_dd_{max_dd:.2f}pct")
            strategy_engine.pending_stop_entries.clear()

    def check_consecutive_losses(self):
        """RULE 5.2.2: 5 consecutive losses -> disable."""
        if self.status != SymbolStatus.ACTIVE:
            return
        if self.consecutive_losses >= 5:
            self._disable(3, f"consec_losses_{self.consecutive_losses}")

    def check_dca_stress(self):
        """RULE 5.2.4: 3+ layer4 trips in 14 days -> disable."""
        if self.status != SymbolStatus.ACTIVE:
            return
        cutoff = self.current_date - timedelta(days=14) if self.current_date else None
        if cutoff is None:
            return
        recent = [t for t in self.layer4_trips_14d if t[0] >= cutoff and t[1]]
        if len(recent) >= 3:
            self._disable(5, f"dca_stress_{len(recent)}_layer4_trips")

    def check_atr_spike(self, atr_14, close):
        """RULE 5.2.3: ATR/close > p95 -> suppress entries (soft)."""
        if close <= 0 or math.isnan(atr_14):
            return False
        atr_pct = atr_14 / close * 100
        self.atr_pct_history_90d.append(atr_pct)
        if len(self.atr_pct_history_90d) < 480:  # need 10+ days
            return False
        p95 = sorted(self.atr_pct_history_90d)[int(len(self.atr_pct_history_90d) * 0.95)]
        return atr_pct > p95

    def on_trade_closed(self, trade):
        """Update risk state after a round-trip completes."""
        if trade.net_pnl >= 0:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

        if trade.max_layers == 4:
            self.layer4_trips_14d.append((self.current_date, True))
        else:
            self.layer4_trips_14d.append((self.current_date, False))

    def shadow_process(self, bar, indicators, strategy_engine):
        """While disabled, compute hypothetical signals/trades for re-enable assessment."""
        # Run strategy logic in shadow mode (no real orders, just signal tracking)
        # This is a lightweight version that only tracks reversal bar signals
        # and hypothetical entry/exit outcomes
        if indicators.is_true_bullish_reversal_bar:
            self.shadow_trades.append(ShadowTrade(
                signal_bar=bar, signal_indicators=indicators))
        # Update shadow trades with hypothetical TP hits
        for st in self.shadow_trades:
            if not st.is_closed:
                st.update(bar, indicators)

    def _disable(self, cooldown_days, reason):
        self.status = SymbolStatus.DISABLED
        self.disabled_until = self.current_date + timedelta(days=cooldown_days)
        self.disable_reason = reason
        self.shadow_trades.clear()
        self.events.append({
            'type': 'disable', 'reason': reason,
            'until': self.disabled_until, 'date': self.current_date})
```

### 6.7 Pseudocode — monitor.py (Live Monitoring Loop)

```python
import time
import asyncio

class LiveMonitor:
    """Live/paper trading monitoring loop."""

    def __init__(self, config, symbols, data_feed, db):
        self.cfg = config
        self.symbols = symbols
        self.data_feed = data_feed  # real-time OHLCV feed
        self.db = db
        self.engines = {}  # symbol -> (IndicatorEngine, StrategyEngine, RiskEngine)
        self._init_engines()

    def _init_engines(self):
        capital_per_symbol = self.cfg.initial_capital / len(self.symbols)
        for sym in self.symbols:
            ie = IndicatorEngine(self.cfg)
            se = StrategyEngine(self.cfg, capital_per_symbol)
            re = RiskEngine(self.cfg, sym, capital_per_symbol)
            self.engines[sym] = (ie, se, re)

    async def run(self):
        """Main loop: wait for candle close, process all symbols."""
        while True:
            # Wait for next 30m candle close
            next_close = self._next_candle_close()
            await asyncio.sleep((next_close - time.time()))

            for sym in self.symbols:
                try:
                    await self._process_symbol(sym)
                except Exception as e:
                    self.db.log_error(sym, str(e))

            # Compute and store portfolio metrics
            self._update_portfolio_metrics()

            # Check re-enable conditions for disabled symbols
            self._check_re_enables()

    async def _process_symbol(self, sym):
        ie, se, re = self.engines[sym]

        # Fetch latest closed candle
        bar = await self.data_feed.get_latest_bar(sym, '30m')

        # Day boundary
        if re.current_date is None or bar.timestamp.date() != re.current_date:
            re.on_new_day(se.equity, bar.timestamp.date())

        # Disabled?
        if re.is_disabled(bar.timestamp.date()):
            indicators = ie.compute(bar)
            re.shadow_process(bar, indicators, se)
            self.db.log_bar(sym, bar, indicators, se, re)
            return

        # Compute indicators
        indicators = ie.compute(bar)

        # ATR spike
        atr_suppressed = re.check_atr_spike(indicators.atr_14, bar.close)
        in_window = not atr_suppressed  # live mode: always in window unless suppressed

        # Process strategy
        fills = se.process_bar(bar, indicators, 0, in_window)

        # In LIVE mode: translate fills to exchange orders
        for fill in fills:
            if fill.order_id.startswith('entry'):
                await self._place_exchange_order(sym, 'buy', fill)
            elif fill.order_id.startswith('exit_'):
                await self._place_exchange_order(sym, 'sell', fill)

        # Risk checks
        re.update_daily_pnl(se.equity, fills)
        re.check_daily_loss(se)
        re.check_rolling_drawdown(se)
        re.check_consecutive_losses()
        re.check_dca_stress()

        # If just disabled, cancel exchange orders
        if re.status == SymbolStatus.DISABLED:
            await self._cancel_exchange_orders(sym)

        # Logging
        self.db.log_bar(sym, bar, indicators, se, re)
        for fill in fills:
            self.db.log_fill(sym, fill)

    def _check_re_enables(self):
        """Daily check for symbol re-enable (run at UTC midnight)."""
        today = datetime.utcnow().date()
        for sym in self.symbols:
            _, _, re = self.engines[sym]
            if re.status in (SymbolStatus.DISABLED, SymbolStatus.COOLDOWN_COMPLETE):
                re.is_disabled(today)  # triggers re-enable check internally

    def _update_portfolio_metrics(self):
        """Compute and log portfolio-level KPIs."""
        total_equity = sum(se.equity for _, se, _ in self.engines.values())
        active_count = sum(1 for _, _, re in self.engines.values()
                          if re.status == SymbolStatus.ACTIVE)
        disabled_count = len(self.symbols) - active_count
        self.db.log_portfolio_snapshot(total_equity, active_count, disabled_count)

    def _next_candle_close(self):
        """Return Unix timestamp of next 30m candle close."""
        now = time.time()
        interval = 1800  # 30 minutes in seconds
        return (now // interval + 1) * interval + 5  # +5s buffer for exchange delay

    async def _place_exchange_order(self, sym, side, fill):
        """Translate fill into live exchange order (paper or real)."""
        # For paper mode: just log it
        # For live mode: use exchange API (e.g., ccxt)
        pass

    async def _cancel_exchange_orders(self, sym):
        """Cancel all pending orders on exchange for disabled symbol."""
        pass
```

### 6.8 Configuration Module

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class StrategyConfig:
    # Strategy parameters (match Pine defaults)
    lowest_bars: int = 7
    layer2_pct: float = 4.0
    layer3_pct: float = 10.0
    layer4_pct: float = 22.0
    position_size_multiplier: float = 2.0
    atr_mult: float = 2.0
    enable_ao: bool = False
    enable_mfi: bool = False

    # Execution
    commission_rate: float = 0.001       # 0.1%
    tick_size: float = 0.01              # default; override per symbol
    max_pyramiding: int = 4

    # Capital
    initial_capital: float = 10000.0

    # Timing
    start_time: datetime = datetime(2025, 1, 1)
    end_time: datetime = datetime(2026, 1, 1)

    # Kill-switch thresholds
    daily_loss_threshold_pct: float = -10.0
    daily_loss_cooldown_days: int = 3
    rolling_dd_threshold_pct: float = 15.0
    rolling_dd_cooldown_days: int = 5
    max_consecutive_losses: int = 5
    consec_loss_cooldown_days: int = 3
    atr_spike_percentile: float = 95.0
    atr_spike_lookback_days: int = 90
    dca_stress_max_layer4: int = 3
    dca_stress_lookback_days: int = 14
    dca_stress_cooldown_days: int = 5

    # Re-enable
    re_enable_min_shadow_trades: int = 3
    re_enable_reduced_alloc_days: int = 7
    re_enable_reduced_alloc_pct: float = 0.5
```

---

## Appendix A: Quick Reference — Kill-Switch Summary Table

| # | Rule | Trigger | Action | Cooldown | Re-enable |
|---|------|---------|--------|----------|-----------|
| 5.1 | Daily Loss | realized PnL <= -10% of day-start equity | Disable symbol, cancel pending entries | 3 days | Cooldown + shadow expectancy > 0 + min 3 shadow trades |
| 5.2.1 | Rolling DD | 14-day max DD > 15% | Disable symbol, cancel pending entries | 5 days | Same as 5.1 |
| 5.2.2 | Consecutive Losses | 5+ losing round-trips in a row | Disable symbol | 3 days | Same as 5.1 |
| 5.2.3 | ATR Spike | ATR/close > 95th pct of 90-day history | Suppress new entries (soft) | None | Auto when ATR/close <= p95 |
| 5.2.4 | DCA Stress | 3+ layer-4 round-trips in 14 days | Disable symbol | 5 days | Same as 5.1 |

## Appendix B: Execution Order Per Bar (Canonical)

```
1. Fetch bar OHLCV
2. Check day boundary → reset daily PnL if new day
3. Check symbol disabled → if yes, run shadow mode, skip to step 12
4. Compute indicators (SMMA, Alligator, ATR, AO, MFI, isLowestBar, isTrueBullishReversalBar)
5. Process pending stop entries (fill if triggered)
6. Process pending limit exits (fill if triggered)
7. Update equity (cash + mark-to-market)
8. Update signal state (confirmation/invalidation levels, crossover/crossunder reset)
9. Detect layer transitions (opentrades changes)
10. Compute TP level
11. Place new entry orders (if conditions met and not suppressed)
12. Place/update exit orders
13. End-of-bar: reset currentLayer if opentrades == 0
14. Risk checks (daily loss, rolling DD, consecutive losses, DCA stress, ATR spike)
15. Log bar state
16. If fills occurred: log fills, update trade records
```

---

*End of specification.*
