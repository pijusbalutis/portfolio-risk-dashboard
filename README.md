
Python backtest of an 8-ETF portfolio (2015–2025) compared with
buy-and-hold and a 60/40 benchmark, using real Yahoo Finance data.

<img width="1468" height="830" alt="Screenshot 2026-10-04 at 17 41 14" src="https://github.com/user-attachments/assets/06a309e6-088a-48bd-9862-3fb4e7858b1c" />

**[View the live interactive dashboard](https://pijusbalutis.github.io/portfolio-risk-dashboard/reports/dashboard.html)**

## Key findings
- Diversified portfolio: 7.92% CAGR, 9.72% volatility, −20.7% max drawdown
- 60/40 benchmark: 8.94% CAGR, 10.93% volatility
- Diversification lowered risk but also returns, as US stocks dominated 2015–2025

## What it does
- Daily backtest with monthly rebalancing and transaction costs
- CAGR, Sharpe, Sortino, drawdown, beta and risk contribution
- Interactive HTML dashboard

## How to run
Open the notebook in Google Colab and click Runtime → Run all.

The code is in `Portfolio_Lab_Results/`.
