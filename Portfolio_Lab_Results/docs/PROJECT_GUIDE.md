# Multi-Asset Portfolio Performance and Risk Dashboard

This guide covers the complete project specification and implemented research workflow. The source files and Colab notebook contain the full implementation.

## 1. Project overview

Build a reproducible research system that answers:

- How did a multi-asset allocation perform?
- Which assets produced its profits and losses?
- How much risk came from each asset?
- Did rebalancing improve outcomes after trading costs?
- How did the portfolio compare with a 60/40 benchmark?
- How would current holdings respond to specified shocks?

The implemented default universe is SPY, VEA, VWO, AGG, IEF, TIP, GLD and VNQ. Target weights are 30%, 15%, 5%, 20%, 10%, 5%, 10% and 5%, respectively. The example allocation is a research configuration, not an optimized recommendation.

There are three explicit data modes: deterministic synthetic demonstration, Yahoo adjusted-price download, and user-supplied CSV. API failure never silently switches a historical run to simulated data.

Scope: daily observations; long-only fully invested portfolios; one USD reporting currency; no external cash flows; fractional total-return units.

## 2. Real-world finance use case

An asset-management analyst receives a proposed allocation and needs an auditable portfolio review for an investment meeting. The system produces performance, risk, allocation and cost analysis using a consistent set of assumptions.

Applications include investment reporting, wealth-management allocation reviews, benchmark comparisons, treasury investment analysis and interview research demonstrations.

The project emphasizes return accounting and interpretation. An attractive performance chart alone cannot establish that a portfolio is suitable, investable or likely to outperform.

## 3. System architecture

| Layer | Implementation | Responsibility |
|---|---|---|
| Configuration | portfolio_lab/config.py | Dates, weights, capital, costs, frequency and validation |
| Data adapters | portfolio_lab/data.py | Demo, Yahoo, CSV, FRED, caching and provenance |
| Validation | clean_prices | Common history, numeric checks, duplicate/gap checks |
| Simulation | portfolio_lab/engine.py | Holdings, close rebalances, cost funding, ledgers |
| Analytics | portfolio_lab/analytics.py | Metrics, drawdowns, contribution and scenario analysis |
| Visualization | portfolio_lab/charts.py | Ten consistent Matplotlib charts |
| Dashboard | portfolio_lab/report.py | Offline HTML, embedded SVG, native browser interaction |
| Orchestration | portfolio_lab/pipeline.py | Run configuration and reproducible export bundle |
| Entry points | notebook / __main__.py | Colab teaching workflow and local command line |
| Verification | tests/ | Hand-calculated financial cases and provider-contract fixtures |

~~~mermaid
flowchart TD
    A["Configuration"] --> B["Data adapters and cache"]
    B --> C["Price validation"]
    C --> D["Holdings engine"]
    D --> E["Risk and performance analytics"]
    E --> F["Charts and HTML dashboard"]
    E --> G["CSV outputs and manifest"]
    H["Financial correctness tests"] -.-> C
    H -.-> D
    H -.-> E
~~~

Calculation functions are separate from API calls and rendering. This makes the accounting reusable and allows tests to run without network access.

## 4. Required APIs and data sources

| Source | Required? | Authentication | Fields used |
|---|---|---|---|
| Synthetic generator | Default demonstration | None | Reproducible positive total-return indices |
| Yahoo Finance via yfinance | For live-price mode | No API key in this adapter | Daily adjusted close; adjustment option set explicitly |
| FRED DGS3MO | Optional risk-free proxy | FRED API key | Date and annualized 3-month Treasury yield |
| User CSV | Optional alternative | None | Date and one adjusted-price column per ticker |

The CSV must use a Date header, ISO dates, and finite positive USD adjusted-price columns matching all configured portfolio and benchmark tickers. A sample is included in examples/synthetic_adjusted_prices.csv. Its values are synthetic.

SEC EDGAR is not needed for a price-based portfolio dashboard. Alpha Vantage, Financial Modeling Prep and Massive can be added as alternate adapters, but are not required dependencies.

Official source references:

1. [yfinance download parameters](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html): explicitly control adjustments and understand its column schema.
2. [yfinance usage notes](https://github.com/ranaroussi/yfinance): unofficial package and provider data-use considerations.
3. [FRED observations API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html): request parameters and observation format.
4. [DGS3MO definition](https://fred.stlouisfed.org/series/DGS3MO): yields quoted in percent per annum on an investment basis.

Historical adjusted prices are not a point-in-time security master. This fixed ETF universe does not remove selection or survivorship bias.

## 5. Required Python libraries

| Library | Purpose | Required in offline mode? |
|---|---|---|
| numpy | Vectorized returns, holdings arrays and covariance algebra | Yes |
| pandas | Time-series alignment, period aggregation and tables | Yes |
| matplotlib | Professional static and embedded SVG charts | Yes |
| yfinance | Yahoo historical-price adapter | Only for Yahoo mode |
| Python standard library | Configuration, HTTP, caching, JSON, CLI, tests and ZIP export | Included |
| IPython.display | Optional inline display in Colab/Jupyter | Bundled with Colab |

The HTML report uses small native JavaScript controls and embedded SVG. It does not need a chart CDN, a server, Plotly, Streamlit or a running Python session after export.

## 6. Folder/file structure

| Path | Purpose |
|---|---|
| README.md | Entry point, local setup, Colab instructions and assumptions |
| requirements.txt | Small numerical and plotting dependency set |
| requirements-live.txt | Optional Yahoo dependency |
| pyproject.toml | Installable package metadata and console entry point |
| notebooks/Multi_Asset_Portfolio_Dashboard.ipynb | Complete self-contained Colab workflow |
| portfolio_lab/config.py | Validated portfolio settings |
| portfolio_lab/data.py | Providers, cache, cleaning and risk-free alignment |
| portfolio_lab/engine.py | Holdings-based portfolio simulation |
| portfolio_lab/analytics.py | Performance, tail risk, drawdown and attribution |
| portfolio_lab/charts.py | Consistent chart factory and PNG/SVG exports |
| portfolio_lab/report.py | Standalone interactive HTML |
| portfolio_lab/pipeline.py | Analysis orchestration and output manifest |
| portfolio_lab/__main__.py | Local command-line entry point |
| tests/test_finance.py | Financial identities and hand-calculated examples |
| tests/test_data.py | Data quality, API schemas, caching and timing |
| tools/build_notebook.py | Regenerate the notebook from the source files |
| docs/PROJECT_GUIDE.md | This complete project design |
| docs/VALIDATION.md | Executed checks and verification limitations |
| examples/ | Labelled synthetic data and example charts |
| data/cache/ | Checksummed provider snapshots, ignored by git |
| reports/ | Generated dashboard, tables, manifest and figures |
| .github/workflows/tests.yml | Automatic correctness checks after publishing |

Colab creates the same reusable package structure in its runtime. It is intentionally possible to move the project into a conventional repository without rewriting the financial logic.

## 7. Step-by-step build guide

1. **Select the scope.** Fix the reporting currency, date range, invested starting value, target weights, benchmark and trading-cost convention.
2. **Validate configuration.** Reject negative or non-finite weights and require weights to sum to one.
3. **Collect data.** Choose one explicit source mode; retrieve all portfolio and benchmark symbols together.
4. **Audit observations.** Reject duplicate dates, nonnumeric/nonpositive prices and interior gaps. Trim to common history and report the trimming.
5. **Build return series.** Divide consecutive adjusted prices; never substitute missing observations with zero returns.
6. **Run holdings accounting.** Apply each day's price changes to previous holdings, then rebalance at the scheduled close.
7. **Fund costs.** Solve for investable wealth after costs instead of allocating money that has already been spent.
8. **Compare strategies.** Run configured rebalancing, buy-and-hold and the monthly benchmark on identical dates.
9. **Compute risk-free proxies.** Use the explicit constant assumption or strictly backward-aligned FRED yields.
10. **Calculate analytics.** Produce growth, risk, tail losses, benchmark metrics, rolling series and contributions.
11. **Verify identities.** Asset contributions plus costs must equal daily portfolio returns; dollar contributions must equal total P&L.
12. **Render outputs.** Save the HTML dashboard, professional figures, numeric CSVs and provenance manifest.
13. **Write the research interpretation.** Explain what drove results and how conclusions change with costs, dates, weights and benchmarks.

Estimated learning-and-build effort: roughly 20–35 focused hours with basic Python and finance knowledge. The supplied implementation is complete; understanding and extending it is the substantive learning work.

## 8. Data collection pipeline

Yahoo downloads use auto_adjust=False and select Adj Close explicitly. The parser handles flat single-ticker output and both common orientations of MultiIndex columns. Raw Close is never silently substituted.

Queries are keyed by provider, fields, symbols and date interval. Completed data and metadata files are written atomically. Metadata includes collection time, query, adjustment convention and SHA-256. The cache is a frozen snapshot until an explicit refresh is requested.

Downloads have bounded retries. A failed live request returns an actionable error. It does not claim stale or generated data are current observations.

FRED requests use the observations API and a 30-day initial lookback. Credentials stay in environment variables or Colab Secrets. API keys are excluded from logs, cache metadata and manifests.

The manifest records the actual data interval, requested configuration, data-source flags, validation findings, software versions, and checksums for exported CSVs.

## 9. Data cleaning and feature engineering

**Dates:** parse, normalize daily labels, remove timezone information while preserving exchange-local dates, reject duplicates, sort, and apply the configured start-inclusive/end-exclusive interval.

**Prices:** require finite, positive observations; select all portfolio and benchmark symbols; trim to the first and last dates where the full universe exists. Interior missing cells are errors. Gaps longer than seven calendar days require investigation.

**Diagnostics:** flag unusually large daily moves over 35%, trimmed history and stale trailing coverage. These checks do not constitute a complete exchange-calendar or corporate-action audit.

**Features:** simple asset returns, portfolio net returns, excess returns, drawdowns, monthly compounded returns, rolling volatility, rolling Sharpe, rolling beta, gross turnover, P&L and risk contributions.

The model uses adjusted total-return units. It does not combine adjusted returns with separately added cash dividends.

For the FRED proxy, a yield observation must strictly predate the start of the return interval. Forward-carrying a known rate is allowed for a maximum of 10 calendar days; prices are never carried forward. The latest FRED vintage is used, not a historical ALFRED reconstruction.

## 10. Core models and algorithms

### Asset and portfolio returns

For adjusted price P, asset return is r(i,t) = P(i,t) / P(i,t−1) − 1.

If H(i,t−1) is the prior closing dollar holding, pre-trade value is:

H_before(i,t) = H(i,t−1) × [1 + r(i,t)].

Today's market P&L is H(i,t−1) × r(i,t). Rebalancing at today's close cannot change that already-earned P&L.

### Transaction-cost equation

For pre-trade values H_before, target weights w and per-dollar cost c, solve:

V_after + c × Σ |w(i) × V_after − H_before(i)| = V_before.

The implementation uses a bounded 60-step bisection. Post-trade values are w × V_after. This pays the cost from portfolio value and preserves the accounting identity.

Gross turnover = gross bought-plus-sold notional / pre-trade NAV. A convention that halves turnover would produce a different statistic; this project explicitly uses gross turnover.

### Rebalancing

Calendar rules are monthly, quarterly, annual or none. Trading happens at the first observed session's close in a new period. Target weights apply to the following return interval. The benchmark always rebalances monthly, which is recorded explicitly.

### Attribution

Daily return contribution from asset i is asset P&L(i,t) / NAV(t−1). Cost contribution is −fees(t) / NAV(t−1). Their sum equals the portfolio's net daily return.

Dollar P&L attribution sums each asset's daily dollar P&L and adds trading costs as a negative component. Contributions sum exactly to ending NAV minus starting capital. Summing daily return contributions would not generally equal a compounded total return.

### Risk contribution

Given current weights w and annualized covariance Σ:

- Portfolio volatility: σ = sqrt(wᵀΣw).
- Component volatility: RC(i) = w(i) × (Σw)(i) / σ.
- Share of volatility: RC(i) / σ.

The components sum to total volatility. Negative contributions may represent hedging and are retained. Covariance uses the full observed sample for descriptive analysis; it is never fed into earlier backtest decisions.

### Stress scenarios

For hypothetical simple asset shocks s, portfolio shock is wᵀs. Scenario definitions are exported. They are instantaneous assumptions without assigned probabilities. Custom tickers disable the default scenario panel until explicit shocks are supplied.

### Complexity and optimization

Return arrays are computed once. The holdings loop is O(T×N), which is appropriate because holdings are path-dependent. Cost solving occurs only on rebalance dates; each solve is O(60×N). The default eight-asset daily dataset comfortably fits a standard Colab CPU runtime.

## 11. Visualizations and dashboard components

The standalone HTML dashboard has four tabs:

1. **Overview:** selected-strategy KPI cards, interactive NAV chart, benchmark comparison, drawdowns and monthly heatmap.
2. **Risk:** rolling volatility, asset correlation, capital-versus-risk contribution, and hypothetical stress outcomes.
3. **Attribution:** allocation history and reconciled dollar P&L.
4. **Data & assumptions:** source provenance, cash-rate assumption, cost conventions and data-quality findings.

The strategy selector updates KPI cards and highlights a curve. The 1Y/3Y/All buttons change the plotted range only; KPI cards explicitly remain full-sample statistics. Hover displays exact values. Detailed asset panels describe the configured Portfolio.

Ten figures are exported in PNG and SVG: growth, drawdowns, rolling volatility, monthly returns, correlation, weights, P&L attribution, risk contributions, stress, and a composite executive summary.

## 12. Performance metrics

Let A = 252, e = portfolio return minus matching cash-return proxy, b = benchmark excess return, and a = portfolio return minus benchmark return. Standard deviations use sample ddof=1.

| Metric | Convention |
|---|---|
| Total return | Ending NAV / starting NAV − 1 |
| CAGR | (Ending NAV / starting NAV)^(365.25 / elapsed calendar days) − 1 |
| Annualized volatility | Daily return standard deviation × sqrt(A) |
| Sharpe ratio | Mean(e) / standard deviation(e) × sqrt(A) |
| Sortino ratio | Mean(e) × sqrt(A) / sqrt(mean(min(e,0)^2)); includes all days in the denominator average |
| Drawdown | NAV / running maximum NAV − 1 |
| Maximum drawdown | Most negative drawdown |
| Calmar ratio | CAGR / absolute maximum drawdown |
| Tracking error | Standard deviation(a) × sqrt(A) |
| Information ratio | Mean(a) / standard deviation(a) × sqrt(A) |
| Beta | Covariance(e,b) / variance(b) |
| Arithmetic annual alpha | [Mean(e) − beta × Mean(b)] × A |
| Historical daily VaR | Configured quantile of daily loss L = −return |
| Historical daily ES | Mean observed loss at or above the VaR threshold |
| Positive-day fraction | Fraction of portfolio net returns greater than zero |
| Longest drawdown | Peak-to-recovery calendar days, or peak-to-end for an ongoing episode |
| Annual gross turnover | Sum of gross turnover / elapsed calendar years |
| Fees | Sum of dollar rebalancing costs |

VaR and ES use an empirical daily loss convention: positive values mean losses; negative values can occur if even the relevant tail consists of gains. These are descriptive tail estimates, not a bank regulatory-capital implementation. Undefined ratios remain NaN/N/A.

The fixed risk-free proxy compounds by actual calendar days using actual/365.25. FRED DGS3MO is an annualized quoted yield; treating it as an effective annual cash rate is a documented approximation, not an observed Treasury investment return. No standalone cash sleeve earns this proxy in portfolio NAV.

## 13. Final deliverables

- A standalone, cell-labelled Colab notebook with full visible module source.
- A reusable installable Python package and CLI.
- This 15-part guide and setup README.
- A financial correctness and data-contract test suite plus CI workflow.
- A labelled synthetic input example and executive-summary chart.
- An interactive HTML dashboard that works offline.
- Daily ledgers, positions, weights, returns, monthly tables, rolling metrics, drawdown episodes, contributions and stress CSVs.
- Ten PNG/SVG charts and a manifest containing assumptions, software versions and data checksums.

Interpretation template for a research memo: **question → data and dates → assumptions → performance and risk findings → attribution → sensitivity analysis → limitations → next experiment**. Report observations actually measured in your run.

## 14. Résumé description

**Project title:** Multi-Asset Portfolio Performance & Risk Analytics — Python

**Suggested bullet:**

Built a reproducible eight-asset portfolio analytics system in Python, implementing holdings-based rebalancing, transaction-cost accounting, benchmark comparisons, and performance/risk attribution; delivered a self-contained dashboard, documented data pipelines, and automated financial correctness tests.

**Technical keywords:** Python, NumPy, pandas, Matplotlib, time-series analysis, portfolio accounting, risk analytics, API integration, testing, Google Colab.

**Interview talking points:**

- Why do buy-and-hold weights drift?
- How can an apparently small cost-model shortcut violate self-financing?
- Why do adjusted prices and separately added dividends double-count distributions?
- Why do missing-price fills alter measured volatility and correlation?
- Why is the arithmetic sum of daily return contributions different from a compounded total return?
- How does the selected benchmark change beta and active-risk interpretation?

Quantify returns or speed improvements in a résumé only after measuring and documenting them yourself.

## 15. Potential upgrades

| Upgrade | Finance benefit | Engineering work |
|---|---|---|
| External cash flows, TWR and money-weighted IRR | Support investor account reporting | Cash-flow ledger and unitization |
| Explicit cash sleeve | Model uninvested balances and financing | Cash accrual and portfolio cash constraints |
| FX translation and currency attribution | Support portfolios with different listing currencies | FX calendar alignment and local/base return decomposition |
| Historical security master | Reduce selection/survivorship problems | Membership, identifier changes and delisting records |
| Exchange-calendar validation | Detect missing sessions across the whole universe | Integrate exchange calendars and holiday logic |
| ALFRED vintages | Reconstruct historical economic information | Vintage-aware observation storage |
| Factor attribution | Separate systematic exposure from residual performance | Factor data and robust regression inference |
| Covariance shrinkage and risk budgeting | Explore more stable allocation methods | Rolling estimation and constrained optimization |
| Spread/impact models | Improve trading-cost realism | Liquidity data and nonlinear execution assumptions |
| Bootstrap confidence intervals | Quantify estimate uncertainty | Block resampling and statistical reporting |
| Broker reconciliation | Compare research output with account records | Trade/cash/dividend ledger and reconciliation |
| Scheduled deployment | Generate recurring reports | Durable compute, monitoring, secrets and provider entitlements |

Start with cost, allocation and date-range sensitivity analysis before adding more complex predictive models.
