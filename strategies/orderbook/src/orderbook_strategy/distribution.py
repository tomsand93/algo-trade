"""Distribution models for directional probability estimation."""

from collections import deque
from dataclasses import dataclass, field
from math import erf, exp, log, sqrt
from typing import Optional

import numpy as np
from scipy import stats


@dataclass
class NormalDist:
    """Online Normal distribution with Welford's algorithm."""
    n: int = 0
    mean: float = 0.0
    m2: float = 0.0  # Sum of squared differences from mean

    def update(self, x: float) -> None:
        """Update with new sample."""
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        delta2 = x - self.mean
        self.m2 += delta * delta2

    @property
    def variance(self) -> float:
        """Sample variance."""
        if self.n < 2:
            return 0.0
        return self.m2 / (self.n - 1)

    @property
    def std(self) -> float:
        """Sample standard deviation."""
        return sqrt(self.variance)

    def cdf(self, x: float) -> float:
        """Cumulative distribution function."""
        if self.n < 2:
            return 0.5
        return 0.5 * (1 + erf((x - self.mean) / (self.std * sqrt(2))))

    def p_up(self) -> float:
        """P(return > 0)."""
        return 1 - self.cdf(0)

    def p_down(self) -> float:
        """P(return < 0)."""
        return self.cdf(0)


@dataclass
class HistogramDist:
    """Histogram-based distribution with CDF estimation."""
    buffer: deque = field(default_factory=lambda: deque(maxlen=2000))
    bins: int = 60
    _edges: Optional[np.ndarray] = None
    _counts: Optional[np.ndarray] = None

    def update(self, x: float) -> None:
        """Update with new sample."""
        self.buffer.append(x)
        # Recompute histogram on each update (simpler than incremental)
        if len(self.buffer) > 10:
            arr = np.array(self.buffer)
            self._counts, self._edges = np.histogram(arr, bins=self.bins)

    def _ensure_histogram(self) -> None:
        """Ensure histogram is computed."""
        if self._counts is None and len(self.buffer) > 0:
            arr = np.array(self.buffer)
            self._counts, self._edges = np.histogram(arr, bins=self.bins)

    def cdf(self, x: float) -> float:
        """Empirical CDF."""
        self._ensure_histogram()
        if self._counts is None or len(self._counts) == 0:
            return 0.5

        # Find which bin x falls into
        for i, edge in enumerate(self._edges[1:], 1):
            if x <= edge:
                # Sum counts up to this bin
                cumulative = self._counts[:i].sum()
                return cumulative / self._counts.sum()

        return 1.0

    def p_up(self) -> float:
        """P(return > 0)."""
        return 1 - self.cdf(0)

    def p_down(self) -> float:
        """P(return < 0)."""
        return self.cdf(0)


@dataclass
class KDEDist:
    """Kernel Density Estimation distribution."""
    buffer: deque = field(default_factory=lambda: deque(maxlen=1000))
    _kde: Optional[stats.gaussian_kde] = None
    _xmin: float = 0.0
    _xmax: float = 0.0

    def update(self, x: float) -> None:
        """Update with new sample."""
        self.buffer.append(x)
        # Recompute KDE periodically
        if len(self.buffer) % 50 == 0 or self._kde is None:
            self._recompute_kde()

    def _recompute_kde(self) -> None:
        """Recompute KDE from buffer."""
        if len(self.buffer) < 10:
            return
        arr = np.array(self.buffer)
        self._kde = stats.gaussian_kde(arr)
        self._xmin = arr.min()
        self._xmax = arr.max()

    def cdf(self, x: float) -> float:
        """CDF via KDE integration."""
        if self._kde is None or len(self.buffer) < 10:
            return 0.5

        # Integrate KDE from -inf to x
        # Use numeric integration over reasonable range
        from scipy.integrate import quad

        def integrand(t):
            return float(self._kde([t])[0])

        result, _ = quad(integrand, self._xmin - 3, min(x, self._xmax + 3))
        return min(max(result, 0.0), 1.0)

    def p_up(self) -> float:
        """P(return > 0)."""
        return 1 - self.cdf(0)

    def p_down(self) -> float:
        """P(return < 0)."""
        return self.cdf(0)


@dataclass
class ConditionalDist:
    """Conditional distribution manager with state-based bucketing."""
    dist_type: str = "normal"
    sigma_floor: float = 1.0e-6
    min_samples: int = 200
    use_conditioning: bool = True
    lookback: int = 2000
    hist_bins: int = 60

    # State buckets
    _global: NormalDist | HistogramDist | KDEDist = field(init=False)
    _states: dict[str, NormalDist | HistogramDist | KDEDist] = field(
        default_factory=dict
    )

    def __post_init__(self):
        """Initialize distributions."""
        if self.dist_type == "normal":
            self._global = NormalDist()
        elif self.dist_type == "hist":
            self._global = HistogramDist(buffer=deque(maxlen=self.lookback), bins=self.hist_bins)
        elif self.dist_type == "kde":
            self._global = KDEDist(buffer=deque(maxlen=self.lookback))
        else:
            raise ValueError(f"Unknown dist_type: {self.dist_type}")

    def _make_dist(self) -> NormalDist | HistogramDist | KDEDist:
        """Create new distribution instance."""
        if self.dist_type == "normal":
            return NormalDist()
        elif self.dist_type == "hist":
            return HistogramDist(buffer=deque(maxlen=self.lookback), bins=self.hist_bins)
        else:
            return KDEDist(buffer=deque(maxlen=self.lookback))

    def get_state_key(self, imbalance: float, delta: float) -> str:
        """Compute state key for conditioning."""
        if not self.use_conditioning:
            return "global"

        imb_sign = "pos" if imbalance > 0 else ("neg" if imbalance < 0 else "zero")
        delta_sign = "pos" if delta > 0 else ("neg" if delta < 0 else "zero")
        return f"{imb_sign}_{delta_sign}"

    def update(self, ret: float, state_key: str) -> None:
        """Update distribution with new return sample."""
        # Update global
        self._global.update(ret)

        # Update state-specific
        if state_key != "global":
            if state_key not in self._states:
                self._states[state_key] = self._make_dist()
            self._states[state_key].update(ret)

    def get_probabilities(
        self, imbalance: float, delta: float
    ) -> tuple[float, float, str, int]:
        """Get (p_up, p_down, state_key, sample_count)."""
        state_key = self.get_state_key(imbalance, delta)

        # Use state-specific if enough samples
        if state_key in self._states:
            dist = self._states[state_key]
            n = dist.n if hasattr(dist, "n") else len(dist.buffer)
        else:
            dist = self._global
            n = dist.n if hasattr(dist, "n") else len(dist.buffer)

        p_up = dist.p_up()
        p_down = dist.p_down()

        return p_up, p_down, state_key, n


def compute_horizon_return(start_mid: float, end_mid: float) -> float:
    """Compute log return over horizon."""
    if start_mid <= 0 or end_mid <= 0:
        return 0.0
    return log(end_mid / start_mid)
