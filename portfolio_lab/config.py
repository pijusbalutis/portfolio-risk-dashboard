"""Validated configuration. Weights are fractions; transaction costs are basis points."""

from dataclasses import asdict, dataclass, field
import math
import pandas as pd

DEFAULT_WEIGHTS = {
    "SPY": 0.30, "VEA": 0.15, "VWO": 0.05, "AGG": 0.20,
    "IEF": 0.10, "TIP": 0.05, "GLD": 0.10, "VNQ": 0.05,
}
ASSET_NAMES = {
    "SPY": "US equities", "VEA": "Developed ex-US equities",
    "VWO": "Emerging-market equities", "AGG": "US aggregate bonds",
    "IEF": "Intermediate Treasuries", "TIP": "Inflation-linked bonds",
    "GLD": "Gold", "VNQ": "US listed real estate",
}


@dataclass(frozen=True)
class Config:
    """All portfolio assumptions in one place; no hidden normalization of weights."""

    start: str = "2015-01-01"
    end: str = "2026-01-01"  # Exclusive, matching Yahoo's historical download API.
    weights: dict[str, float] = field(default_factory=lambda: DEFAULT_WEIGHTS.copy())
    benchmark_weights: dict[str, float] = field(
        default_factory=lambda: {"SPY": 0.60, "AGG": 0.40}
    )
    initial_capital: float = 100_000.0
    rebalance: str = "monthly"
    cost_bps: float = 5.0  # Applied to EACH dollar bought or sold.
    annualization: int = 252
    rolling_window: int = 126
    min_observations: int = 60
    fixed_rf_annual: float = 0.02  # Explicit assumption, not a historical observation.
    confidence: float = 0.95
    seed: int = 42

    def __post_init__(self):
        start, end = pd.Timestamp(self.start), pd.Timestamp(self.end)
        if pd.isna(start) or pd.isna(end) or start >= end:
            raise ValueError("start must be before exclusive end.")
        if start.tz is not None or end.tz is not None:
            raise ValueError("Use timezone-naive date strings in Config.")
        for name, weights in (("weights", self.weights),
                              ("benchmark_weights", self.benchmark_weights)):
            if not weights or any(not isinstance(k, str) or not k for k in weights):
                raise ValueError(f"{name} must contain nonempty ticker names.")
            if any(not math.isfinite(v) or v < 0 for v in weights.values()):
                raise ValueError(f"{name} must be finite and nonnegative.")
            if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-10):
                raise ValueError(f"{name} must sum to 1.0; received {sum(weights.values())}.")
        if not math.isfinite(self.initial_capital) or self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive and finite.")
        if not math.isfinite(self.cost_bps) or not 0 <= self.cost_bps <= 1000:
            raise ValueError("cost_bps must be between 0 and 1,000.")
        if self.rebalance not in {"monthly", "quarterly", "annual", "none"}:
            raise ValueError("Unsupported rebalance frequency.")
        if self.annualization <= 1 or self.rolling_window < 2 or self.min_observations < 3:
            raise ValueError("Invalid annualization, window, or observation count.")
        if not math.isfinite(self.fixed_rf_annual) or self.fixed_rf_annual <= -1:
            raise ValueError("The effective annual risk-free assumption must exceed -100%.")
        if not 0.5 < self.confidence < 1:
            raise ValueError("confidence must lie between 0.5 and 1.")

    @property
    def tickers(self) -> list[str]:
        return sorted(set(self.weights) | set(self.benchmark_weights))

    def to_dict(self) -> dict:
        return asdict(self)
