"""Self-financing holdings engine with costs, drift, and exact P&L attribution."""

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class Backtest:
    name: str
    nav: pd.Series
    returns: pd.Series
    weights: pd.DataFrame
    positions: pd.DataFrame
    pnl: pd.DataFrame
    contributions: pd.DataFrame
    ledger: pd.DataFrame


def rebalance_due(current: pd.Timestamp, previous: pd.Timestamp, frequency: str) -> bool:
    """Trade at the close of the first observed session in a new calendar period."""
    if frequency == "none":
        return False
    if frequency == "monthly":
        return (current.year, current.month) != (previous.year, previous.month)
    if frequency == "quarterly":
        return (current.year, current.quarter) != (previous.year, previous.quarter)
    if frequency == "annual":
        return current.year != previous.year
    raise ValueError(f"Unknown frequency: {frequency}")


def rebalance_with_cost(values: np.ndarray, target: np.ndarray,
                        cost_rate: float) -> tuple[np.ndarray, float, float]:
    """Solve V_after + c * sum(abs(w*V_after - holdings_before)) = V_before.

    Bisection is stable because 0 <= c < 1 and long-only target weights sum to one.
    Computing costs from pre-fee target weights would miss the extra selling
    necessary to fund those costs.
    """
    total = float(values.sum())
    if cost_rate == 0:
        after = total * target
        return after, 0.0, float(np.abs(after - values).sum())
    lower, upper = 0.0, total
    for _ in range(60):
        middle = (lower + upper) / 2
        balance = middle + cost_rate * np.abs(middle * target - values).sum() - total
        if balance > 0:
            upper = middle
        else:
            lower = middle
    after = ((lower + upper) / 2) * target
    traded = float(np.abs(after - values).sum())
    return after, float(total - after.sum()), traded


def backtest(prices: pd.DataFrame, target_weights: dict[str, float],
             initial_capital: float = 100_000, frequency: str = "monthly",
             cost_bps: float = 5.0, name: str = "Portfolio") -> Backtest:
    """Simulate an already-invested long-only portfolio, using total-return units.

    The first close is the endowed baseline; entry and final liquidation costs
    are excluded symmetrically. No external cash flows, leverage, tax, or cash
    sleeve. Today's return uses yesterday's holdings; a close rebalance affects
    the next interval. Adjusted units are not broker-executable share counts.
    """
    symbols = list(target_weights)
    if frequency not in {"monthly", "quarterly", "annual", "none"}:
        raise ValueError("Unsupported frequency.")
    if not np.isfinite(initial_capital) or initial_capital <= 0:
        raise ValueError("initial_capital must be finite and positive.")
    if not np.isfinite(cost_bps) or not 0 <= cost_bps <= 1000:
        raise ValueError("cost_bps must lie in [0, 1000].")
    target = np.array(list(target_weights.values()), dtype=float)
    if target.size == 0 or not np.isfinite(target).all() or (target < 0).any():
        raise ValueError("Weights must be finite and nonnegative.")
    if not np.isclose(target.sum(), 1.0, rtol=0, atol=1e-10):
        raise ValueError("Weights must sum to one.")
    if len(prices) < 2 or prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("Need two or more unique, increasing price observations.")
    p = prices.loc[:, symbols].to_numpy(dtype=float)
    if not np.isfinite(p).all() or (p <= 0).any():
        raise ValueError("Prices must be finite, nonmissing, and positive.")
    # Price ratios are computed once; holdings must evolve sequentially.
    changes = p[1:] / p[:-1] - 1
    n, m = p.shape
    positions = np.zeros((n, m))
    pnl = np.zeros((n, m))
    contributions = np.zeros((n, m + 1))
    nav, fees, turnover, gross_traded = (np.zeros(n) for _ in range(4))
    rebalanced = np.zeros(n, dtype=bool)
    positions[0] = initial_capital * target
    nav[0] = initial_capital
    rate = cost_bps / 10_000
    for row in range(1, n):
        pnl[row] = positions[row - 1] * changes[row - 1]
        before = positions[row - 1] + pnl[row]
        contributions[row, :m] = pnl[row] / nav[row - 1]
        if rebalance_due(prices.index[row], prices.index[row - 1], frequency):
            after, fee, traded = rebalance_with_cost(before, target, rate)
            positions[row] = after
            fees[row], gross_traded[row] = fee, traded
            turnover[row] = traded / before.sum()  # Gross traded notional, not half-turnover.
            rebalanced[row] = True
        else:
            positions[row] = before
        nav[row] = positions[row].sum()
        contributions[row, -1] = -fees[row] / nav[row - 1]
    index = prices.index
    nav_series = pd.Series(nav, index=index, name=name)
    returns = nav_series.pct_change(fill_method=None).iloc[1:]
    contribution_frame = pd.DataFrame(
        contributions, index=index, columns=symbols + ["Trading costs"]
    )
    np.testing.assert_allclose(
        contribution_frame.iloc[1:].sum(axis=1), returns, atol=2e-12, rtol=1e-10,
        err_msg="Daily return attribution failed to reconcile."
    )
    total_pnl = float(pnl.sum() - fees.sum())
    np.testing.assert_allclose(total_pnl, nav[-1] - initial_capital, atol=1e-7, rtol=1e-10)
    ledger = pd.DataFrame({
        "nav": nav, "fees": fees, "gross_traded_notional": gross_traded,
        "gross_turnover": turnover, "rebalance": rebalanced,
    }, index=index)
    return Backtest(
        name=name, nav=nav_series, returns=returns,
        weights=pd.DataFrame(positions / nav[:, None], index=index, columns=symbols),
        positions=pd.DataFrame(positions, index=index, columns=symbols),
        pnl=pd.DataFrame(pnl, index=index, columns=symbols),
        contributions=contribution_frame, ledger=ledger,
    )
