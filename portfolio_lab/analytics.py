"""Return, tail-risk, attribution and scenario calculations with explicit conventions."""

import numpy as np
import pandas as pd
from .engine import Backtest


def safe_ratio(numerator: float, denominator: float) -> float:
    """Undefined ratios are NaN, never silently zero or infinite."""
    if not np.isfinite(denominator) or abs(denominator) < 1e-14:
        return float("nan")
    return float(numerator / denominator)


def drawdown(nav: pd.Series) -> pd.Series:
    return (nav / nav.cummax() - 1).rename("drawdown")


def drawdown_episodes(nav: pd.Series) -> pd.DataFrame:
    """Peak-to-recovery calendar durations; ongoing episodes have no recovery date."""
    episodes, peak_date, peak_value = [], nav.index[0], float(nav.iloc[0])
    trough_date, trough_value, active = peak_date, peak_value, False
    for date, value in nav.iloc[1:].items():
        value = float(value)
        if value >= peak_value * (1 - 1e-12):
            if active:
                episodes.append({"peak": peak_date, "trough": trough_date, "recovery": date,
                                 "depth": trough_value / peak_value - 1,
                                 "duration_days": (date - peak_date).days, "recovered": True})
            peak_date, peak_value = date, value
            trough_date, trough_value, active = date, value, False
        else:
            active = True
            if value < trough_value:
                trough_date, trough_value = date, value
    if active:
        episodes.append({"peak": peak_date, "trough": trough_date, "recovery": pd.NaT,
                         "depth": trough_value / peak_value - 1,
                         "duration_days": (nav.index[-1] - peak_date).days, "recovered": False})
    return pd.DataFrame(episodes, columns=[
        "peak", "trough", "recovery", "depth", "duration_days", "recovered"
    ]).sort_values("depth").reset_index(drop=True)


def periodic_returns(nav: pd.Series, frequency: str = "ME") -> pd.Series:
    """Compound from period-end NAV; include the initial partial period explicitly."""
    ends = nav.resample(frequency).last().dropna()
    beginning = ends.shift(1)
    beginning.iloc[0] = nav.iloc[0]
    return ends / beginning - 1


def monthly_heatmap(nav: pd.Series) -> pd.DataFrame:
    returns = periodic_returns(nav)
    frame = pd.DataFrame({"year": returns.index.year, "month": returns.index.month,
                          "return": returns.values})
    return frame.pivot(index="year", columns="month", values="return").reindex(columns=range(1, 13))


def summary_metrics(result: Backtest, benchmark: Backtest, risk_free: pd.Series,
                    annualization: int = 252, confidence: float = .95) -> dict[str, float]:
    """CAGR uses elapsed calendar time; daily moment estimators use 252 sessions/year."""
    returns = result.returns
    if not returns.index.equals(benchmark.returns.index) or not returns.index.equals(risk_free.index):
        raise ValueError("Portfolio, benchmark and risk-free returns must align exactly.")
    if len(returns) < 2 or not np.isfinite(risk_free.to_numpy()).all():
        raise ValueError("Metrics require finite, aligned return observations.")
    years = (result.nav.index[-1] - result.nav.index[0]).days / 365.25
    if years <= 0:
        raise ValueError("Performance interval has zero calendar length.")
    excess = returns - risk_free
    benchmark_excess = benchmark.returns - risk_free
    active = returns - benchmark.returns
    volatility = float(returns.std(ddof=1) * np.sqrt(annualization))
    excess_vol = float(excess.std(ddof=1) * np.sqrt(annualization))
    downside = float(np.sqrt(np.mean(np.minimum(excess.to_numpy(), 0) ** 2) * annualization))
    total_return = float(result.nav.iloc[-1] / result.nav.iloc[0] - 1)
    cagr = float(np.expm1(np.log1p(total_return) / years))
    dd = drawdown(result.nav)
    beta = safe_ratio(float(excess.cov(benchmark_excess)), float(benchmark_excess.var(ddof=1)))
    alpha = float((excess.mean() - beta * benchmark_excess.mean()) * annualization)
    tracking_error = float(active.std(ddof=1) * np.sqrt(annualization))
    losses = -returns.to_numpy()
    var = float(np.quantile(losses, confidence))
    es = float(losses[losses >= var].mean())
    episodes = drawdown_episodes(result.nav)
    return {
        "total_return": total_return, "cagr": cagr, "annual_volatility": volatility,
        "sharpe": safe_ratio(float(excess.mean() * annualization), excess_vol),
        "sortino": safe_ratio(float(excess.mean() * annualization), downside),
        "max_drawdown": float(dd.min()), "calmar": safe_ratio(cagr, abs(float(dd.min()))),
        "tracking_error": tracking_error,
        "information_ratio": safe_ratio(float(active.mean() * annualization), tracking_error),
        "beta": beta, "alpha_annual_arithmetic": alpha,
        "var_daily": var, "expected_shortfall_daily": es,
        "positive_day_fraction": float((returns > 0).mean()),
        "longest_drawdown_days": float(episodes.duration_days.max()) if len(episodes) else 0.,
        "total_fees": float(result.ledger.fees.sum()),
        "annual_gross_turnover": float(result.ledger.gross_turnover.sum() / years),
        "ending_nav": float(result.nav.iloc[-1]),
        "return_observations": float(len(returns)),
    }


def rolling_metrics(result: Backtest, benchmark: Backtest, risk_free: pd.Series,
                    window: int = 126, annualization: int = 252) -> pd.DataFrame:
    excess, b_excess = result.returns - risk_free, benchmark.returns - risk_free
    std = excess.rolling(window).std(ddof=1).replace(0, np.nan)
    b_var = b_excess.rolling(window).var(ddof=1).replace(0, np.nan)
    return pd.DataFrame({
        "annual_volatility": result.returns.rolling(window).std(ddof=1) * np.sqrt(annualization),
        "sharpe": excess.rolling(window).mean() / std * np.sqrt(annualization),
        "beta": excess.rolling(window).cov(b_excess) / b_var,
    })


def pnl_attribution(result: Backtest) -> pd.Series:
    """Dollar contributions add exactly to terminal NAV minus initial capital."""
    values = result.pnl.sum()
    values.loc["Trading costs"] = -result.ledger.fees.sum()
    np.testing.assert_allclose(values.sum(), result.nav.iloc[-1] - result.nav.iloc[0],
                               rtol=1e-10, atol=1e-7)
    return values.rename("pnl_usd")


def risk_contributions(asset_returns: pd.DataFrame, weights: pd.Series,
                       annualization: int = 252) -> pd.DataFrame:
    """Euler volatility allocation at CURRENT weights using full-sample covariance.

    This is an ex-post risk description, not a predictive model or a backtest input.
    Negative components can reflect hedging; they must not be clipped.
    """
    covariance = asset_returns.loc[:, weights.index].cov().to_numpy() * annualization
    w = weights.to_numpy()
    variance = float(w @ covariance @ w)
    sigma = np.sqrt(max(variance, 0))
    components = w * (covariance @ w) / sigma if sigma > 1e-14 else np.full(len(w), np.nan)
    fraction = components / sigma if sigma > 1e-14 else np.full(len(w), np.nan)
    return pd.DataFrame({"weight": w, "volatility_contribution": components,
                         "risk_fraction": fraction}, index=weights.index)


def stress_scenarios(weights: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Illustrative instantaneous shocks; no asserted probabilities or historical labels."""
    assumptions = {
        "Equity selloff": {"SPY": -.30, "VEA": -.32, "VWO": -.38, "AGG": .03,
                           "IEF": .06, "TIP": -.02, "GLD": .08, "VNQ": -.35},
        "Rates + inflation shock": {"SPY": -.15, "VEA": -.15, "VWO": -.18, "AGG": -.08,
                                    "IEF": -.12, "TIP": -.06, "GLD": .04, "VNQ": -.20},
        "Broad risk rally": {"SPY": .20, "VEA": .18, "VWO": .22, "AGG": .03,
                             "IEF": .02, "TIP": .04, "GLD": -.05, "VNQ": .20},
    }
    shocks = pd.DataFrame(assumptions).T
    missing = set(weights.index) - set(shocks.columns)
    if missing:
        # Custom assets must receive explicit shock assumptions rather than zero shocks.
        return pd.DataFrame(), pd.Series(dtype=float, name="scenario_return")
    shocks = shocks.loc[:, weights.index]
    return shocks, shocks.mul(weights, axis=1).sum(axis=1).rename("scenario_return")
