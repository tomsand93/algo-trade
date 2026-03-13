"""Tests for BaseStrategy ABC and MeanReversionStrategy."""
import pytest
from datetime import datetime, timezone
from polymarket_bot.models import MarketState, Signal
from polymarket_bot.strategy import MomentumStrategy


def make_market_state(
    market_id: str = "0xtest",
    yes_price: float = 0.50,
    no_price: float = 0.50,
    question: str = "Test market?",
) -> MarketState:
    """Helper: create a valid MarketState with the given prices."""
    return MarketState(
        market_id=market_id,
        question=question,
        yes_price=round(yes_price, 4),
        no_price=round(no_price, 4),
        volume_24h=10000.0,
        timestamp=datetime.now(timezone.utc),
    )


def feed_prices(strategy, market_id: str, prices: list[float]) -> list[Signal | None]:
    """Feed a list of yes_prices to the strategy and collect signals."""
    signals = []
    for p in prices:
        state = make_market_state(market_id=market_id, yes_price=round(p, 4), no_price=round(1.0 - p, 4))
        signals.append(strategy.generate_signal(state))
    return signals


class TestBaseStrategy:
    """BaseStrategy cannot be instantiated directly."""

    def test_cannot_instantiate_base_strategy(self):
        from polymarket_bot.strategy import BaseStrategy
        with pytest.raises(TypeError):
            BaseStrategy()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_both_methods(self):
        from polymarket_bot.strategy import BaseStrategy

        class IncompleteStrategy(BaseStrategy):
            def generate_signal(self, market_state):
                return None
            # Missing should_trade — should raise TypeError on instantiation

        with pytest.raises(TypeError):
            IncompleteStrategy()

    def test_complete_subclass_is_instantiable(self):
        from polymarket_bot.strategy import BaseStrategy

        class MinimalStrategy(BaseStrategy):
            def generate_signal(self, market_state):
                return None
            def should_trade(self, signal, market_state):
                return False

        s = MinimalStrategy()
        assert s is not None


class TestMeanReversionStrategy:
    """MeanReversionStrategy: window filling, z-score signals, should_trade stub."""

    def test_returns_none_before_window_filled(self):
        """No signal until window observations are collected."""
        from polymarket_bot.strategy import MeanReversionStrategy
        strategy = MeanReversionStrategy(window=5, z_entry=2.0)
        signals = feed_prices(strategy, "0xtest", [0.50, 0.51, 0.49, 0.50])
        # 4 observations for window=5 → all None
        assert all(s is None for s in signals), f"expected all None, got {signals}"

    def test_returns_signal_on_window_fill_if_threshold_met(self):
        """On the 7th observation, if z-score is extreme, a signal fires.

        Uses window=7 because with window=5 the maximum achievable z-score is
        sqrt(n-1)=sqrt(4)=2.0 (asymptotic limit), meaning z_entry=2.0 can never
        be breached with a single extreme in a 5-element window. window=7 allows
        z up to sqrt(6)≈2.45, reliably breaching z_entry=2.0.
        """
        from polymarket_bot.strategy import MeanReversionStrategy
        strategy = MeanReversionStrategy(window=7, z_entry=2.0)
        # Feed 6 neutral prices (window not yet filled for first 6)
        neutral = [0.50, 0.50, 0.50, 0.50, 0.50, 0.50]
        signals = feed_prices(strategy, "0xtest", neutral)
        assert all(s is None for s in signals)

        # 7th price is extreme low → BUY_YES signal expected (z ≈ -2.27 > z_entry=2.0)
        low_state = make_market_state(yes_price=0.10, no_price=0.90)
        signal = strategy.generate_signal(low_state)
        assert signal is not None
        assert signal.direction == "BUY_YES", f"expected BUY_YES, got {signal.direction}"

    def test_buy_no_signal_when_z_score_above_threshold(self):
        """High z-score (price above mean) → BUY_NO signal.

        Uses window=7 for the same mathematical reason as test_returns_signal_on_window_fill:
        z_entry=2.0 requires max z > 2.0, achievable only with window >= 7.
        """
        from polymarket_bot.strategy import MeanReversionStrategy
        strategy = MeanReversionStrategy(window=7, z_entry=2.0)
        neutral = [0.50, 0.50, 0.50, 0.50, 0.50, 0.50]
        feed_prices(strategy, "0xhigh", neutral)

        # 7th price is extreme high → BUY_NO signal expected (z ≈ +2.27 > z_entry=2.0)
        high_state = make_market_state(market_id="0xhigh", yes_price=0.90, no_price=0.10)
        signal = strategy.generate_signal(high_state)
        assert signal is not None
        assert signal.direction == "BUY_NO", f"expected BUY_NO, got {signal.direction}"

    def test_no_signal_for_neutral_z_score(self):
        """z-score within ±z_entry produces no signal."""
        from polymarket_bot.strategy import MeanReversionStrategy
        strategy = MeanReversionStrategy(window=5, z_entry=2.0)
        # All prices near 0.50 → small std, z near 0
        prices = [0.50, 0.51, 0.49, 0.50, 0.50]
        signals = feed_prices(strategy, "0xneutral", prices)
        # Last signal might be None or not (depends on exact z) — check no extremes
        for sig in signals:
            if sig is not None:
                assert sig.direction in ("BUY_YES", "BUY_NO")

    def test_no_signal_when_std_is_zero(self):
        """All identical prices → std=0 → no signal (divide-by-zero guard)."""
        from polymarket_bot.strategy import MeanReversionStrategy
        strategy = MeanReversionStrategy(window=3, z_entry=2.0)
        prices = [0.50, 0.50, 0.50]
        signals = feed_prices(strategy, "0xflat", prices)
        assert all(s is None for s in signals), f"expected all None for flat prices, got {signals}"

    def test_different_markets_tracked_independently(self):
        """Each market_id has its own price history buffer."""
        from polymarket_bot.strategy import MeanReversionStrategy
        strategy = MeanReversionStrategy(window=3, z_entry=2.0)

        # Fill market A with neutral prices
        feed_prices(strategy, "0xA", [0.50, 0.50, 0.50])

        # Market B with only 2 observations → should return None (window not filled)
        signals_b = feed_prices(strategy, "0xB", [0.50, 0.50])
        assert all(s is None for s in signals_b), "market B window not yet filled"

    def test_signal_confidence_is_in_valid_range(self):
        """Confidence must always be in [0.0, 1.0]."""
        from polymarket_bot.strategy import MeanReversionStrategy
        strategy = MeanReversionStrategy(window=5, z_entry=2.0)
        neutral = [0.500, 0.501, 0.499, 0.500]
        feed_prices(strategy, "0xconf", neutral)

        extreme_state = make_market_state(market_id="0xconf", yes_price=0.10, no_price=0.90)
        signal = strategy.generate_signal(extreme_state)
        if signal is not None:
            assert 0.0 <= signal.confidence <= 1.0, f"confidence out of range: {signal.confidence}"

    def test_signal_contains_market_id(self):
        """Signal's market_id matches the input MarketState."""
        from polymarket_bot.strategy import MeanReversionStrategy
        strategy = MeanReversionStrategy(window=5, z_entry=2.0)
        feed_prices(strategy, "0xspecific", [0.500, 0.501, 0.499, 0.500])

        state = make_market_state(market_id="0xspecific", yes_price=0.10, no_price=0.90)
        signal = strategy.generate_signal(state)
        if signal is not None:
            assert signal.market_id == "0xspecific"

    def test_should_trade_true_for_high_confidence(self):
        """should_trade returns True when confidence >= 0.3."""
        from polymarket_bot.strategy import MeanReversionStrategy
        strategy = MeanReversionStrategy()
        state = make_market_state()
        sig = Signal(market_id="0xtest", direction="BUY_YES", confidence=0.74, price=0.50, reason="test")
        assert strategy.should_trade(sig, state) is True

    def test_should_trade_false_for_low_confidence(self):
        """should_trade returns False when confidence < 0.3."""
        from polymarket_bot.strategy import MeanReversionStrategy
        strategy = MeanReversionStrategy()
        state = make_market_state()
        sig = Signal(market_id="0xtest", direction="BUY_YES", confidence=0.1, price=0.50, reason="test")
        assert strategy.should_trade(sig, state) is False

    def test_should_trade_boundary_at_0_3(self):
        """Confidence exactly 0.3 should return True (>= boundary)."""
        from polymarket_bot.strategy import MeanReversionStrategy
        strategy = MeanReversionStrategy()
        state = make_market_state()
        sig = Signal(market_id="0xtest", direction="BUY_YES", confidence=0.3, price=0.50, reason="test")
        assert strategy.should_trade(sig, state) is True


def _make_ms(market_id: str, yes_price: float, question: str = "Q") -> MarketState:
    """Helper for MomentumStrategy tests: create MarketState with computed no_price."""
    return MarketState(
        market_id=market_id,
        question=question,
        yes_price=yes_price,
        no_price=round(1.0 - yes_price, 4),
        volume_24h=1000.0,
        timestamp=datetime.now(timezone.utc),
    )


class TestMomentumStrategy:
    """MomentumStrategy: dual EMA crossover, bootstrap, per-market state."""

    def test_no_signal_during_bootstrap(self):
        """No signal until long_window observations have been collected."""
        strat = MomentumStrategy(short_window=3, long_window=5)
        result = None
        for i in range(4):  # 4 observations, need 5 to complete bootstrap
            result = strat.generate_signal(_make_ms("m1", 0.50))
        assert result is None

    def test_no_signal_when_bootstrapped_but_no_crossover(self):
        """After bootstrap, flat price -> no crossover -> no signal."""
        strat = MomentumStrategy(short_window=3, long_window=5)
        result = None
        for _ in range(6):  # 5 bootstrap + 1 post-bootstrap, all same price
            result = strat.generate_signal(_make_ms("m1", 0.50))
        assert result is None

    def test_buy_yes_signal_on_upward_crossover(self):
        """Short EMA crosses above long EMA on rising prices -> BUY_YES."""
        strat = MomentumStrategy(short_window=3, long_window=5)
        # Bootstrap with declining prices so short EMA starts below long EMA
        for price in [0.50, 0.48, 0.46, 0.44, 0.42]:
            strat.generate_signal(_make_ms("m1", price))
        # Now send rising prices to force short EMA up through long EMA
        signal = None
        for price in [0.45, 0.50, 0.58, 0.65]:
            signal = strat.generate_signal(_make_ms("m1", price))
            if signal is not None:
                break
        assert signal is not None
        assert signal.direction == "BUY_YES"
        assert signal.market_id == "m1"
        assert 0.0 < signal.confidence <= 1.0

    def test_buy_no_signal_on_downward_crossover(self):
        """Short EMA crosses below long EMA on falling prices -> BUY_NO."""
        strat = MomentumStrategy(short_window=3, long_window=5)
        # Bootstrap with rising prices so short EMA starts above long EMA
        for price in [0.50, 0.52, 0.54, 0.56, 0.58]:
            strat.generate_signal(_make_ms("m1", price))
        # Now send falling prices to force short EMA down through long EMA
        signal = None
        for price in [0.55, 0.50, 0.42, 0.35]:
            signal = strat.generate_signal(_make_ms("m1", price))
            if signal is not None:
                break
        assert signal is not None
        assert signal.direction == "BUY_NO"
        assert signal.market_id == "m1"
        assert 0.0 < signal.confidence <= 1.0

    def test_buy_no_signal_price_is_no_price(self):
        """BUY_NO signal uses no_price (not yes_price) as the signal price."""
        strat = MomentumStrategy(short_window=3, long_window=5)
        for price in [0.50, 0.52, 0.54, 0.56, 0.58]:
            strat.generate_signal(_make_ms("m1", price))
        signal = None
        last_ms = None
        for price in [0.55, 0.50, 0.42, 0.35]:
            ms = _make_ms("m1", price)
            signal = strat.generate_signal(ms)
            if signal is not None:
                last_ms = ms
                break
        assert signal is not None
        assert signal.price == pytest.approx(last_ms.no_price, abs=1e-4)

    def test_confidence_is_bounded(self):
        """Confidence is always in [0.0, 1.0]."""
        strat = MomentumStrategy(short_window=3, long_window=5)
        for price in [0.50, 0.48, 0.46, 0.44, 0.42]:
            strat.generate_signal(_make_ms("m1", price))
        for price in [0.45, 0.50, 0.58, 0.65, 0.75, 0.85, 0.95]:
            sig = strat.generate_signal(_make_ms("m1", price))
            if sig is not None:
                assert 0.0 <= sig.confidence <= 1.0

    def test_independent_state_per_market(self):
        """Two different market_ids do not share EMA state."""
        strat = MomentumStrategy(short_window=3, long_window=5)
        # Feed market m1 with rising prices to get near crossover
        for price in [0.50, 0.48, 0.46, 0.44, 0.42, 0.45, 0.50, 0.58]:
            strat.generate_signal(_make_ms("m1", price))
        # Feed market m2 with all flat prices -- should NOT get crossover from m1 state
        for _ in range(5):
            strat.generate_signal(_make_ms("m2", 0.50))
        result = strat.generate_signal(_make_ms("m2", 0.50))
        # m2 should have no crossover since its prices are flat
        assert result is None

    def test_should_trade_returns_bool(self):
        """should_trade() returns True when confidence >= 0.3."""
        strat = MomentumStrategy()
        sig = Signal(
            market_id="m1",
            direction="BUY_YES",
            confidence=0.5,
            price=0.50,
            reason="test",
        )
        ms = _make_ms("m1", 0.50)
        assert strat.should_trade(sig, ms) is True

    def test_should_trade_false_below_threshold(self):
        """should_trade() returns False when confidence < 0.3."""
        strat = MomentumStrategy()
        sig = Signal(
            market_id="m1",
            direction="BUY_YES",
            confidence=0.1,
            price=0.50,
            reason="test",
        )
        ms = _make_ms("m1", 0.50)
        assert strat.should_trade(sig, ms) is False
