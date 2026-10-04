# Verification record

## Executed checks

- **34 automated tests passed** using Python's standard-library unittest runner.
- **All 21 Colab code cells executed successfully** in order in a clean local directory. The execution harness implements the notebook's standard %%writefile cells and executes the remaining Python in a shared namespace.
- The notebook's embedded financial/data test suite passed.
- End-to-end synthetic analysis produced the HTML dashboard, CSV tables, manifest, chart exports, sensitivity experiment and downloadable result bundle.
- Source files compiled successfully.
- Generated charts were visually inspected for legibility, clipping, labels and source identification.
- Dashboard JavaScript was checked with a dependency-free DOM-contract harness: initial render, strategy KPI selection, chart ranges, tab switching, hover tooltips and narrow-width SVG coordinates.

## Financial cases covered

1. Buy-and-hold results match independent fixed-unit arithmetic.
2. Weights drift after relative price movements.
3. A close rebalance cannot change the return earned before that close.
4. Cost funding matches hand-derived two-asset and full-rotation solutions.
5. Positions add to NAV and weights add to one.
6. Dollar P&L and daily return contributions reconcile.
7. Changes to future prices do not change past NAV.
8. Constant prices produce no economically meaningful turnover or costs.
9. Invalid long-only weights are rejected.
10. Drawdown depth, recovery and ongoing durations are handled.
11. Monthly returns compound to the whole-period result.
12. An identical benchmark gives beta one and zero active tracking error.
13. Undefined ratios remain NaN rather than becoming infinite.
14. Historical tail metrics use the correct loss sign.
15. CAGR uses elapsed calendar time.
16. Sortino uses an unconditional lower-partial-moment denominator.
17. Euler component risks sum to total volatility.
18. Risk-free proxies accrue over actual calendar intervals.
19. A FRED quote must predate the start of the return interval.
20. Duplicate dates, nonpositive prices, infinite values and interior gaps fail explicitly.
21. Yahoo adjusted-close schema variants are parsed without silently using raw close.
22. Caches are reused and source failures do not become synthetic data.

## Environment

The calculation core was exercised with Python 3.12, NumPy 2.3.5, pandas 2.2.3 and Matplotlib 3.10.8. A run's manifest records the versions actually used in that environment.

## Verification boundaries

- Live Yahoo and FRED calls were **not executed end to end** in the build environment. Optional package installation was unavailable, and no user API key was supplied. Yahoo adapter schemas and error behavior were tested with deterministic fixtures.
- The notebook was computationally executed with a local cell harness, **not inside an authenticated Google Colab session**. Colab Secrets, its download UI and notebook iframe rendering need a user-side Colab run.
- A Chromium executable was unavailable, so a real browser layout test could not be completed. JavaScript behavior was checked with the DOM-contract harness; static PNG charts were visually inspected.
- Synthetic paths establish software behavior, not an empirical investment result.
- The included tests do not establish production trading suitability or exhaustive data-provider compatibility.

## Repeat the checks

~~~bash
python -m unittest discover -s tests -v
python -m portfolio_lab --mode demo
python tools/build_notebook.py
python tools/check_notebook.py
node tools/check_dashboard.cjs
~~~

Node is only needed for the optional JavaScript smoke test. Neither the Python application nor the exported HTML needs a Node server.
