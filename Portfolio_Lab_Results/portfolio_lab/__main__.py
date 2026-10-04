"""Command-line entry point: python -m portfolio_lab --mode demo."""

import argparse
import logging
from pathlib import Path
from .config import Config
from .data import DataError
from .pipeline import export_analysis, run_analysis


def main():
    parser = argparse.ArgumentParser(description="Multi-asset performance and risk dashboard")
    parser.add_argument("--mode", choices=["demo", "yahoo", "csv"], default="demo")
    parser.add_argument("--csv", type=Path, help="Adjusted-price CSV for --mode csv")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-01-01", help="Exclusive end date")
    parser.add_argument("--rebalance", choices=["monthly", "quarterly", "annual", "none"], default="monthly")
    parser.add_argument("--cost-bps", type=float, default=5)
    parser.add_argument("--fixed-rf", type=float, default=.02, help="Effective annual decimal rate")
    parser.add_argument("--fred", action="store_true", help="Use FRED_API_KEY from environment")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("reports"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        config = Config(start=args.start, end=args.end, rebalance=args.rebalance,
                        cost_bps=args.cost_bps, fixed_rf_annual=args.fixed_rf)
        analysis = run_analysis(config, mode=args.mode, csv_path=args.csv,
                                use_fred=args.fred, refresh=args.refresh)
        paths = export_analysis(analysis, args.output)
    except (DataError, ValueError, OSError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    print(analysis.metrics[["cagr", "annual_volatility", "sharpe", "max_drawdown"]].round(4))
    print(f"Data source: {analysis.metadata['data']['source']}")
    print(f"Dashboard: {paths['dashboard'].resolve()}")


if __name__ == "__main__":
    main()
