"""Economic invariants and independent hand calculations; no market API calls."""
import unittest
import numpy as np
import pandas as pd
from portfolio_lab.analytics import (drawdown, drawdown_episodes, periodic_returns,
                                     pnl_attribution, risk_contributions, summary_metrics)
from portfolio_lab.data import risk_free_returns
from portfolio_lab.engine import backtest, rebalance_with_cost


def prices(values, dates=None):
    return pd.DataFrame(values, index=pd.to_datetime(dates) if dates else
                        pd.bdate_range("2024-01-02", periods=len(next(iter(values.values())))))


class HoldingsTests(unittest.TestCase):
    def test_buy_and_hold_matches_fixed_units(self):
        p = prices({"A": [100, 200, 100], "B": [100, 100, 100]})
        result = backtest(p, {"A": .5, "B": .5}, 1000, "none", 0)
        np.testing.assert_allclose(result.nav, [1000, 1500, 1000])
        self.assertAlmostEqual(result.weights.iloc[1]["A"], 2 / 3)
        self.assertAlmostEqual(result.returns.iloc[1], -1 / 3)

    def test_close_trade_cannot_change_same_day_pnl(self):
        p = prices({"A": [100, 200, 200], "B": [100, 100, 200]},
                   ["2024-01-31", "2024-02-01", "2024-02-02"])
        result = backtest(p, {"A": .5, "B": .5}, 1000, "monthly", 0)
        np.testing.assert_allclose(result.nav, [1000, 1500, 2250])
        self.assertTrue(result.ledger.rebalance.iloc[1])
        np.testing.assert_allclose(result.weights.iloc[1], [.5, .5])

    def test_cost_solver_matches_two_asset_closed_form(self):
        after, fee, traded = rebalance_with_cost(np.array([600., 400.]), np.array([.5, .5]), .01)
        np.testing.assert_allclose(after, [499., 499.], atol=1e-10)
        self.assertAlmostEqual(fee, 2)
        self.assertAlmostEqual(traded, 200)

    def test_cost_funding_full_rotation(self):
        after, fee, traded = rebalance_with_cost(np.array([1000., 0.]), np.array([0., 1.]), .01)
        expected = 1000 * (1 - .01) / (1 + .01)
        self.assertAlmostEqual(after.sum(), expected)
        self.assertAlmostEqual(fee, .01 * traded)
        self.assertAlmostEqual(after.sum() + fee, 1000)

    def test_reconciles_every_interval_with_costs(self):
        rng = np.random.default_rng(7)
        p = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, .02, (300, 3)), axis=0)),
                         index=pd.bdate_range("2023-01-02", periods=300), columns=list("ABC"))
        result = backtest(p, {"A": .6, "B": .3, "C": .1}, 100_000, "monthly", 20)
        np.testing.assert_allclose(result.contributions.iloc[1:].sum(axis=1), result.returns, atol=1e-12)
        self.assertAlmostEqual(pnl_attribution(result).sum(), result.nav.iloc[-1] - 100_000, places=6)
        np.testing.assert_allclose(result.positions.sum(axis=1), result.nav)
        np.testing.assert_allclose(result.weights.sum(axis=1), 1)
        np.testing.assert_allclose(result.ledger.fees, .002 * result.ledger.gross_traded_notional, atol=1e-8)

    def test_future_changes_do_not_change_prior_nav(self):
        p = prices({"A": [100, 102, 103, 104], "B": [100, 99, 101, 105]})
        first = backtest(p, {"A": .5, "B": .5}, frequency="monthly")
        modified = p.copy()
        modified.iloc[-1] *= 2
        second = backtest(modified, {"A": .5, "B": .5}, frequency="monthly")
        np.testing.assert_allclose(first.nav.iloc[:-1], second.nav.iloc[:-1])

    def test_constant_prices_have_no_trades_or_fees(self):
        p = pd.DataFrame(100., index=pd.bdate_range("2024-01-01", periods=100), columns=["A", "B"])
        result = backtest(p, {"A": .6, "B": .4}, cost_bps=25)
        np.testing.assert_allclose(result.nav, 100_000, atol=1e-8)
        self.assertLess(abs(result.ledger.fees.sum()), 1e-8)

    def test_rejects_leverage_or_negative_weights(self):
        p = prices({"A": [100, 101, 99], "B": [100, 102, 98]})
        for weights in [{"A": 1.1, "B": -.1}, {"A": .4, "B": .4}]:
            with self.assertRaises(ValueError):
                backtest(p, weights)


class AnalyticsTests(unittest.TestCase):
    def test_drawdown_and_recovery(self):
        nav = pd.Series([100, 120, 90, 100, 120, 110],
                        index=pd.date_range("2024-01-01", periods=6))
        self.assertAlmostEqual(drawdown(nav).min(), -.25)
        episodes = drawdown_episodes(nav)
        self.assertEqual(len(episodes), 2)
        self.assertTrue(episodes.iloc[0].recovered)
        self.assertEqual(episodes.iloc[0].duration_days, 3)
        self.assertFalse(episodes.iloc[1].recovered)

    def test_monthly_returns_compound_to_total(self):
        nav = pd.Series([100, 110, 121, 133.1], index=pd.to_datetime([
            "2024-01-15", "2024-01-31", "2024-02-29", "2024-03-15"]))
        monthly = periodic_returns(nav)
        np.testing.assert_allclose(monthly, [.1, .1, .1])
        self.assertAlmostEqual((1 + monthly).prod(), nav.iloc[-1] / nav.iloc[0])

    def test_identical_benchmark_has_beta_one_and_zero_tracking_error(self):
        p = prices({"A": [100, 102, 101, 103, 99, 104]})
        result = backtest(p, {"A": 1}, frequency="none", cost_bps=0)
        rf, _ = risk_free_returns(p.index, 0)
        metrics = summary_metrics(result, result, rf)
        self.assertAlmostEqual(metrics["beta"], 1)
        self.assertAlmostEqual(metrics["tracking_error"], 0)
        self.assertAlmostEqual(metrics["alpha_annual_arithmetic"], 0)
        self.assertTrue(np.isnan(metrics["information_ratio"]))

    def test_constant_returns_do_not_produce_infinite_sharpe(self):
        p = prices({"A": [100, 100, 100, 100]})
        result = backtest(p, {"A": 1})
        rf, _ = risk_free_returns(p.index, 0)
        metrics = summary_metrics(result, result, rf)
        self.assertTrue(np.isnan(metrics["sharpe"]))
        self.assertTrue(np.isnan(metrics["sortino"]))
        self.assertTrue(np.isnan(metrics["calmar"]))

    def test_tail_metrics_have_correct_loss_sign(self):
        p = prices({"A": [100, 90, 99, 89.1, 93.555]})
        result = backtest(p, {"A": 1}, frequency="none", cost_bps=0)
        rf, _ = risk_free_returns(p.index, 0)
        metrics = summary_metrics(result, result, rf)
        self.assertAlmostEqual(metrics["var_daily"], .1)
        self.assertAlmostEqual(metrics["expected_shortfall_daily"], .1)

    def test_cagr_uses_calendar_years(self):
        p = prices({"A": [100, 105, 110]}, ["2023-01-01", "2023-07-01", "2024-01-01"])
        result = backtest(p, {"A": 1}, frequency="none")
        rf, _ = risk_free_returns(p.index, 0)
        metrics = summary_metrics(result, result, rf)
        self.assertAlmostEqual(metrics["cagr"], 1.1 ** (365.25 / 365) - 1)

    def test_sortino_uses_all_observations_in_downside_rms(self):
        p = prices({"A": [100, 110, 99, 108.9, 98.01]})
        result = backtest(p, {"A": 1}, frequency="none")
        rf = pd.Series(.01, index=result.returns.index)
        excess = np.array([.09, -.11, .09, -.11])
        expected = excess.mean() * np.sqrt(252) / np.sqrt(np.mean(np.minimum(excess, 0) ** 2))
        self.assertAlmostEqual(summary_metrics(result, result, rf)["sortino"], expected)

    def test_risk_contributions_sum_to_volatility(self):
        returns = pd.DataFrame({"A": [.02, -.01, .03, -.03], "B": [.01, .01, -.01, -.02]})
        w = pd.Series({"A": .6, "B": .4})
        result = risk_contributions(returns, w)
        expected = np.sqrt(w.values @ (returns.cov().values * 252) @ w.values)
        self.assertAlmostEqual(result.volatility_contribution.sum(), expected)
        self.assertAlmostEqual(result.risk_fraction.sum(), 1)


if __name__ == "__main__":
    unittest.main()
