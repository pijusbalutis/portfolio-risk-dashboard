"""Consistent, publication-ready charts with no network or browser dependency."""

from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, PercentFormatter
from .analytics import drawdown, monthly_heatmap

NAVY, TEAL, BLUE, CORAL = "#142D4E", "#087F8C", "#7B91B4", "#D66A4B"
COLORS = {"Portfolio": TEAL, "Buy & hold": BLUE, "Benchmark": CORAL}
STYLE = {
    "figure.facecolor": "#FAFBFD", "axes.facecolor": "#FAFBFD",
    "axes.edgecolor": "#DCE3EA", "axes.labelcolor": "#566579",
    "text.color": NAVY, "xtick.color": "#566579", "ytick.color": "#566579",
    "font.family": "DejaVu Sans", "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titleweight": "bold", "axes.titlesize": 13,
    "grid.alpha": .40, "grid.color": "#DCE3EA",
    "legend.frameon": False, "savefig.facecolor": "#FAFBFD",
}
MONEY = FuncFormatter(lambda value, _: "$" + f"{value / 1000:,.0f}k")


def _finish(ax, title: str, percent: bool = False):
    ax.set_title(title, loc="left", pad=14)
    ax.grid(axis="y", zorder=0)
    ax.set_axisbelow(True)
    if percent:
        ax.yaxis.set_major_formatter(PercentFormatter(1))


def _nav(ax, analysis):
    for name, result in analysis.results.items():
        ax.plot(result.nav.index, result.nav, label=name, color=COLORS[name],
                lw=2.2 if name == "Portfolio" else 1.35, alpha=.95)
    _finish(ax, "Portfolio value · net of rebalancing costs")
    ax.yaxis.set_major_formatter(MONEY)
    ax.legend(loc="upper left", ncol=3, fontsize=9)


def _drawdowns(ax, analysis):
    for name, result in analysis.results.items():
        values = drawdown(result.nav)
        ax.plot(values.index, values, color=COLORS[name], lw=1.15, label=name)
    _finish(ax, "Drawdowns from prior high", percent=True)


def _rolling_vol(ax, analysis):
    for name, frame in analysis.rolling.items():
        ax.plot(frame.index, frame.annual_volatility, color=COLORS[name], lw=1.25, label=name)
    _finish(ax, f"Rolling volatility · {analysis.config.rolling_window} sessions", percent=True)


def _attribution(ax, analysis):
    data = analysis.attribution.sort_values()
    ax.barh(data.index, data.values, color=[TEAL if v >= 0 else CORAL for v in data])
    ax.axvline(0, lw=.8, color=BLUE)
    ax.xaxis.set_major_formatter(MONEY)
    ax.set_title("P&L attribution · reconciled dollars", loc="left", pad=14)
    ax.grid(axis="x")
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", labelsize=9)


def create_figures(analysis) -> dict[str, plt.Figure]:
    """Create independent figures so both notebook and HTML exports reuse one calculation."""
    figures = {}
    label = "SIMULATED DATA • NOT MARKET PERFORMANCE" if analysis.metadata["data"]["synthetic"] else "HISTORICAL RESEARCH • USD"
    with plt.rc_context(STYLE):
        for key, drawing in [("growth", _nav), ("drawdowns", _drawdowns),
                             ("rolling_volatility", _rolling_vol)]:
            fig, ax = plt.subplots(figsize=(11, 4.3), layout="constrained")
            drawing(ax, analysis)
            fig.suptitle(label, x=.01, ha="left", fontsize=8, color=CORAL, fontweight="bold")
            figures[key] = fig

        fig, ax = plt.subplots(figsize=(10, 5.3), layout="constrained")
        matrix = monthly_heatmap(analysis.results["Portfolio"].nav)
        finite = matrix.to_numpy()[np.isfinite(matrix.to_numpy())]
        limit = max(float(np.abs(finite).max()), .01)
        image = ax.imshow(matrix, cmap="RdYlGn", vmin=-limit, vmax=limit, aspect="auto")
        for row in range(len(matrix)):
            for column in range(12):
                value = matrix.iloc[row, column]
                if np.isfinite(value):
                    ax.text(column, row, f"{value:.1%}", ha="center", va="center", fontsize=8,
                            color="white" if abs(value) > limit * .7 else NAVY)
        ax.set_xticks(range(12), ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        ax.set_yticks(range(len(matrix)), matrix.index.astype(str))
        ax.set_title("Portfolio monthly returns · initial/final months may be partial", loc="left", pad=14)
        fig.colorbar(image, ax=ax, format=PercentFormatter(1), shrink=.8)
        figures["monthly_returns"] = fig

        fig, ax = plt.subplots(figsize=(8, 6), layout="constrained")
        correlation = analysis.prices.pct_change(fill_method=None).iloc[1:].corr()
        image = ax.imshow(correlation, cmap="RdBu_r", vmin=-1, vmax=1)
        for i in range(len(correlation)):
            for j in range(len(correlation)):
                value = correlation.iloc[i, j]
                ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=8,
                        color="white" if abs(value) > .6 else NAVY)
        ax.set_xticks(range(len(correlation)), correlation.columns)
        ax.set_yticks(range(len(correlation)), correlation.index)
        ax.set_title("Asset return correlations · full sample", loc="left", pad=14)
        fig.colorbar(image, ax=ax, shrink=.8)
        figures["correlation"] = fig

        fig, ax = plt.subplots(figsize=(11, 4.8), layout="constrained")
        weights = analysis.results["Portfolio"].weights
        palette = plt.get_cmap("tab20")(np.linspace(0, .85, len(weights.columns)))
        ax.stackplot(weights.index, weights.to_numpy().T, labels=weights.columns,
                     colors=palette, alpha=.90)
        _finish(ax, "Portfolio weights · drift and scheduled rebalancing", percent=True)
        ax.set_ylim(0, 1)
        ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(.5, -.13), fontsize=9)
        figures["weights"] = fig

        fig, ax = plt.subplots(figsize=(9, 4.8), layout="constrained")
        _attribution(ax, analysis)
        figures["pnl_attribution"] = fig

        fig, ax = plt.subplots(figsize=(9, 4.8), layout="constrained")
        risk = analysis.risk
        x = np.arange(len(risk))
        ax.bar(x - .18, risk.weight, .36, label="Capital weight", color=BLUE)
        ax.bar(x + .18, risk.risk_fraction, .36, label="Share of volatility", color=TEAL)
        ax.set_xticks(x, risk.index)
        _finish(ax, "Current allocation vs. full-sample risk contribution", percent=True)
        ax.legend(loc="upper right")
        figures["risk_contributions"] = fig

        fig, ax = plt.subplots(figsize=(10, 4.3), layout="constrained")
        if len(analysis.stress):
            ax.barh(analysis.stress.index, analysis.stress.values,
                    color=[TEAL if v >= 0 else CORAL for v in analysis.stress])
            ax.xaxis.set_major_formatter(PercentFormatter(1))
            ax.axvline(0, color=BLUE, lw=.8)
            ax.grid(axis="x")
        else:
            ax.text(.5, .5, "Define explicit shocks for your custom assets.",
                    ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Illustrative shocks · current holdings · no probabilities", loc="left", pad=14)
        figures["stress"] = fig

        fig = plt.figure(figsize=(14, 10), layout="constrained")
        grid = fig.add_gridspec(3, 2, height_ratios=[.40, 1, 1])
        banner = fig.add_subplot(grid[0, :])
        banner.axis("off")
        banner.text(0, .94, "PORTFOLIO LAB", fontsize=11, fontweight="bold", color=TEAL)
        banner.text(0, .53, "Multi-Asset Performance & Risk", fontsize=23, fontweight="bold")
        banner.text(0, .09, label, fontsize=9, color=CORAL, fontweight="bold")
        metrics = analysis.metrics.loc["Portfolio"]
        for position, (caption, value) in enumerate([
            ("CAGR", f"{metrics.cagr:.2%}"), ("VOLATILITY", f"{metrics.annual_volatility:.2%}"),
            ("SHARPE", f"{metrics.sharpe:.2f}"), ("MAX DRAWDOWN", f"{metrics.max_drawdown:.2%}")
        ]):
            x = .57 + position * .108
            banner.text(x, .61, caption, fontsize=8, color="#566579")
            banner.text(x, .22, value, fontsize=18, fontweight="bold")
        _nav(fig.add_subplot(grid[1, 0]), analysis)
        _drawdowns(fig.add_subplot(grid[1, 1]), analysis)
        _rolling_vol(fig.add_subplot(grid[2, 0]), analysis)
        _attribution(fig.add_subplot(grid[2, 1]), analysis)
        figures["executive_summary"] = fig
        for name, chart in figures.items():
            if name != "executive_summary":
                chart.suptitle(label, x=.01, ha="left", fontsize=8, color=CORAL, fontweight="bold")
    return figures


def save_figures(figures: dict, directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, figure in figures.items():
        path = directory / f"{name}.png"
        figure.savefig(path, dpi=150, bbox_inches="tight")
        figure.savefig(directory / f"{name}.svg", bbox_inches="tight")
        paths[name] = path
    return paths
