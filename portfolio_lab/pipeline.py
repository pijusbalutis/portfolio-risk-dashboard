"""Orchestration and reproducible exports; no data-provider calls inside analytics."""

from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import json
import os
import platform

import numpy as np
import pandas as pd

from .analytics import (monthly_heatmap, pnl_attribution, risk_contributions,
                        rolling_metrics, stress_scenarios, summary_metrics, drawdown_episodes)
from .config import Config
from .data import (DataError, atomic_write, clean_prices, fetch_fred_yields, fetch_yahoo,
                   generate_demo, load_csv, risk_free_returns, utc_now)
from .engine import Backtest, backtest


@dataclass
class Analysis:
    config: Config
    prices: pd.DataFrame
    risk_free: pd.Series
    results: dict[str, Backtest]
    metrics: pd.DataFrame
    rolling: dict[str, pd.DataFrame]
    risk: pd.DataFrame
    attribution: pd.Series
    shocks: pd.DataFrame
    stress: pd.Series
    metadata: dict


def run_analysis(config: Config, mode: str = "demo", cache_dir: Path | str = "data/cache",
                 csv_path: Path | str | None = None, use_fred: bool = False,
                 fred_api_key: str | None = None, refresh: bool = False) -> Analysis:
    """Build three comparable portfolios on an identical common price calendar."""
    cache_dir = Path(cache_dir)
    if mode == "demo":
        bundle = generate_demo(config)
    elif mode == "yahoo":
        bundle = fetch_yahoo(config, cache_dir, refresh)
    elif mode == "csv" and csv_path is not None:
        bundle = load_csv(Path(csv_path))
    else:
        raise DataError("mode must be demo, yahoo, or csv with a supplied csv_path.")
    prices, audit = clean_prices(bundle.prices, config)
    fred_metadata = None
    if use_fred:
        fred = fetch_fred_yields(config, fred_api_key or os.getenv("FRED_API_KEY", ""),
                                cache_dir, refresh)
        rf, rf_metadata = risk_free_returns(prices.index, yields_percent=fred.prices["DGS3MO"])
        fred_metadata = fred.metadata
    else:
        rf, rf_metadata = risk_free_returns(prices.index, config.fixed_rf_annual)
    results = {
        "Portfolio": backtest(prices, config.weights, config.initial_capital,
                              config.rebalance, config.cost_bps, "Portfolio"),
        "Buy & hold": backtest(prices, config.weights, config.initial_capital,
                               "none", config.cost_bps, "Buy & hold"),
        "Benchmark": backtest(prices, config.benchmark_weights, config.initial_capital,
                              "monthly", config.cost_bps, "Benchmark"),
    }
    benchmark = results["Benchmark"]
    metrics = pd.DataFrame({
        name: summary_metrics(result, benchmark, rf, config.annualization, config.confidence)
        for name, result in results.items()
    }).T
    rolling = {
        name: rolling_metrics(result, benchmark, rf, config.rolling_window, config.annualization)
        for name, result in results.items()
    }
    asset_returns = prices.pct_change(fill_method=None).iloc[1:]
    final_weights = results["Portfolio"].weights.iloc[-1]
    risk = risk_contributions(asset_returns, final_weights, config.annualization)
    shocks, stress = stress_scenarios(final_weights)
    metadata = {
        "generated_at_utc": utc_now(), "mode": mode, "data": bundle.metadata,
        "data_quality": audit, "risk_free": rf_metadata, "fred_download": fred_metadata,
        "assumptions": {
            "base_currency": "USD", "long_only": True, "fractional_total_return_units": True,
            "start": "Already invested at first close; entry and liquidation fees excluded.",
            "rebalance": "First observed session of the new period, after its return.",
            "costs": "Basis points on gross bought plus sold notional, funded from NAV.",
            "cash_flows": "None; no leverage, borrowing, tax, or standalone cash sleeve.",
            "benchmark": "Configured benchmark weights, monthly close rebalancing, same cost rate.",
            "covariance": "Full-sample ex-post estimate for descriptive risk attribution.",
        },
    }
    return Analysis(config, prices, rf, results, metrics, rolling, risk,
                    pnl_attribution(results["Portfolio"]), shocks, stress, metadata)


def export_analysis(analysis: Analysis, output_dir: Path | str = "reports") -> dict[str, Path]:
    """Export reusable numeric outputs, provenance, charts, and an offline HTML report."""
    from .charts import create_figures, save_figures
    from .report import write_dashboard
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = {
        "cleaned_prices": analysis.prices, "metrics": analysis.metrics,
        "risk_free_returns": analysis.risk_free, "risk_contributions": analysis.risk,
        "pnl_attribution": analysis.attribution, "scenario_assumptions": analysis.shocks,
        "scenario_results": analysis.stress,
    }
    for name, result in analysis.results.items():
        slug = name.lower().replace(" & ", "_").replace(" ", "_")
        frames.update({
            f"{slug}_ledger": result.ledger, f"{slug}_positions": result.positions,
            f"{slug}_weights": result.weights, f"{slug}_daily_returns": result.returns,
            f"{slug}_return_contributions": result.contributions,
            f"{slug}_monthly_returns": monthly_heatmap(result.nav),
            f"{slug}_drawdowns": drawdown_episodes(result.nav),
            f"{slug}_rolling": analysis.rolling[name],
        })
    paths = {}
    for name, frame in frames.items():
        path = output_dir / f"{name}.csv"
        frame.to_csv(path, index=True, float_format="%.12g")
        paths[name] = path
    versions = {"python": platform.python_version()}
    for package in ("numpy", "pandas", "matplotlib", "yfinance"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "not installed"
    manifest = {**analysis.metadata, "configuration": analysis.config.to_dict(),
                "environment": versions,
                "file_hashes": {p.name: sha256(p.read_bytes()).hexdigest() for p in paths.values()}}
    manifest_path = output_dir / "manifest.json"
    atomic_write(manifest_path, json.dumps(manifest, indent=2))
    paths["manifest"] = manifest_path
    figures = create_figures(analysis)
    paths.update(save_figures(figures, output_dir / "charts"))
    dashboard = output_dir / "dashboard.html"
    write_dashboard(analysis, figures, dashboard)
    paths["dashboard"] = dashboard
    import matplotlib.pyplot as plt
    for figure in figures.values():
        plt.close(figure)
    return paths
