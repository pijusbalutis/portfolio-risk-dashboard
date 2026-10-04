"""Data boundaries, provider schemas, caching, and information timing."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from portfolio_lab.config import Config
from portfolio_lab.data import (DataError, clean_prices, extract_adjusted_close,
    fetch_yahoo, generate_demo, risk_free_returns, fetch_fred_yields)
from portfolio_lab.pipeline import run_analysis


def small_config():
    return Config(start="2024-01-01", end="2024-02-01",
                  weights={"A": .5, "B": .5}, benchmark_weights={"A": 1},
                  min_observations=3, rolling_window=3)


class DataTests(unittest.TestCase):
    def setUp(self):
        self.config = small_config()
        self.p = pd.DataFrame({"A": [100, 101, 102, 103], "B": [100, 99, 101, 102]},
                              index=pd.bdate_range("2024-01-02", periods=4))

    def test_missing_interior_price_fails(self):
        self.p.loc[self.p.index[1], "A"] = np.nan
        with self.assertRaisesRegex(DataError, "Interior"):
            clean_prices(self.p, self.config)

    def test_common_inception_is_trimmed_and_reported(self):
        self.p.loc[self.p.index[0], "A"] = np.nan
        clean, audit = clean_prices(self.p, self.config)
        self.assertEqual(len(clean), 3)
        self.assertEqual(audit["trimmed_rows"], 1)

    def test_duplicate_dates_fail(self):
        with self.assertRaisesRegex(DataError, "Duplicate"):
            clean_prices(pd.concat([self.p, self.p.iloc[[-1]]]), self.config)

    def test_nonpositive_prices_fail(self):
        self.p.iloc[1, 0] = 0
        with self.assertRaisesRegex(DataError, "positive"):
            clean_prices(self.p, self.config)

    def test_infinite_prices_fail(self):
        p = self.p.astype(float)
        p.iloc[1, 0] = np.inf
        with self.assertRaises(DataError):
            clean_prices(p, self.config)

    def test_yahoo_multiindex_field_first(self):
        raw = pd.concat({"Adj Close": self.p, "Close": self.p * 2}, axis=1)
        pd.testing.assert_frame_equal(extract_adjusted_close(raw, ["A", "B"]), self.p)

    def test_yahoo_multiindex_ticker_first(self):
        raw = pd.concat({"Adj Close": self.p, "Close": self.p * 2}, axis=1).swaplevel(axis=1)
        pd.testing.assert_frame_equal(extract_adjusted_close(raw, ["A", "B"]), self.p)

    def test_yahoo_single_ticker_flat_schema(self):
        raw = pd.DataFrame({"Adj Close": [100, 101]}, index=self.p.index[:2])
        self.assertEqual(extract_adjusted_close(raw, ["A"]).columns.tolist(), ["A"])

    def test_raw_close_is_never_silently_substituted(self):
        with self.assertRaisesRegex(DataError, "Adjusted"):
            extract_adjusted_close(pd.concat({"Close": self.p}, axis=1), ["A", "B"])

    def test_cache_round_trip_does_not_call_provider_twice(self):
        calls = []
        def download(*args, **kwargs):
            calls.append(kwargs)
            return pd.concat({"Adj Close": self.p}, axis=1)
        with TemporaryDirectory() as directory:
            first = fetch_yahoo(self.config, Path(directory), downloader=download)
            second = fetch_yahoo(self.config, Path(directory), downloader=download)
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0]["auto_adjust"])
        self.assertTrue(second.metadata["cache_hit"])
        np.testing.assert_allclose(first.prices, second.prices)

    def test_provider_failure_does_not_become_demo_data(self):
        def broken(*args, **kwargs):
            raise ConnectionError("network unavailable")
        with TemporaryDirectory() as directory, patch("portfolio_lab.data.time.sleep"):
            with self.assertRaisesRegex(DataError, "failed after"):
                fetch_yahoo(self.config, Path(directory), downloader=broken)

    def test_constant_risk_free_includes_weekend_accrual(self):
        dates = pd.to_datetime(["2024-01-05", "2024-01-08", "2024-01-09"])
        rf, _ = risk_free_returns(dates, .05)
        np.testing.assert_allclose(rf, [(1.05) ** (3 / 365.25) - 1, (1.05) ** (1 / 365.25) - 1])

    def test_risk_free_uses_quote_strictly_before_interval_start(self):
        dates = pd.to_datetime(["2024-01-05", "2024-01-08", "2024-01-09"])
        yields = pd.Series([2., 20., 50.],
                           index=pd.to_datetime(["2024-01-04", "2024-01-05", "2024-01-08"]))
        rf, _ = risk_free_returns(dates, yields_percent=yields)
        np.testing.assert_allclose(rf, [(1.02) ** (3 / 365.25) - 1, (1.20) ** (1 / 365.25) - 1])

    def test_stale_risk_free_quotes_fail(self):
        yields = pd.Series([5.], index=pd.to_datetime(["2024-01-01"]))
        with self.assertRaisesRegex(DataError, "stale"):
            risk_free_returns(pd.to_datetime(["2024-01-20", "2024-01-21"]), yields_percent=yields)

    def test_fred_requires_explicit_key(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(DataError, "requires"):
                fetch_fred_yields(self.config, "", Path(directory))

    def test_demo_is_deterministic_and_labelled(self):
        first, second = generate_demo(self.config), generate_demo(self.config)
        pd.testing.assert_frame_equal(first.prices, second.prices)
        self.assertTrue(first.metadata["synthetic"])

    def test_invalid_configuration_fails_early(self):
        with self.assertRaises(ValueError):
            Config(weights={"A": .9})
        with self.assertRaises(ValueError):
            Config(cost_bps=-1)
        with self.assertRaises(ValueError):
            Config(start="2025-01-01", end="2024-01-01")

    def test_pipeline_uses_one_common_calendar(self):
        analysis = run_analysis(self.config, mode="demo")
        for result in analysis.results.values():
            self.assertTrue(result.nav.index.equals(analysis.prices.index))
            self.assertTrue(result.returns.index.equals(analysis.risk_free.index))
        self.assertTrue(analysis.metadata["data"]["synthetic"])


if __name__ == "__main__":
    unittest.main()
