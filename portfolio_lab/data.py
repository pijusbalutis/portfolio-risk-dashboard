"""Price adapters, explicit provenance, fail-closed cleaning, and risk-free proxies."""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
from pathlib import Path
import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from .config import Config

LOG = logging.getLogger(__name__)


class DataError(RuntimeError):
    """Actionable provider, schema, or data-quality failure."""


@dataclass
class DataBundle:
    prices: pd.DataFrame
    metadata: dict


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path: Path, content: str) -> None:
    """Replace a completed local file atomically; never leave a partial cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _cache_paths(directory: Path, query: dict) -> tuple[Path, Path]:
    key = sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()[:20]
    return directory / f"{key}.csv", directory / f"{key}.json"


def _load_cache(directory: Path, query: dict) -> DataBundle | None:
    data_path, meta_path = _cache_paths(directory, query)
    if not data_path.exists() or not meta_path.exists():
        return None
    try:
        raw = data_path.read_bytes()
        metadata = json.loads(meta_path.read_text())
        if sha256(raw).hexdigest() != metadata["sha256"]:
            raise ValueError("checksum mismatch")
        prices = pd.read_csv(StringIO(raw.decode()), index_col=0, parse_dates=True)
    except (ValueError, KeyError, OSError) as exc:
        raise DataError("Cache is corrupt. Delete its CSV/JSON pair or force refresh.") from exc
    metadata["cache_hit"] = True
    return DataBundle(prices, metadata)


def _save_cache(directory: Path, query: dict, bundle: DataBundle) -> None:
    data_path, meta_path = _cache_paths(directory, query)
    csv = bundle.prices.to_csv(index_label="Date", float_format="%.12g")
    bundle.metadata["sha256"] = sha256(csv.encode()).hexdigest()
    atomic_write(data_path, csv)
    atomic_write(meta_path, json.dumps(bundle.metadata, indent=2))


def extract_adjusted_close(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Accept Yahoo's flat or either orientation of two-level column schemas."""
    if raw is None or raw.empty:
        raise DataError("Yahoo returned no rows. Check dates, symbols, and connectivity.")
    if isinstance(raw.columns, pd.MultiIndex):
        selected = None
        for level in range(raw.columns.nlevels):
            if "Adj Close" in raw.columns.get_level_values(level):
                selected = raw.xs("Adj Close", axis=1, level=level)
                break
        if selected is None:
            raise DataError("Adjusted close is absent; raw close is not a safe substitute.")
        prices = selected.copy()
    elif "Adj Close" in raw.columns and len(tickers) == 1:
        prices = raw[["Adj Close"]].rename(columns={"Adj Close": tickers[0]})
    else:
        raise DataError("Unrecognized Yahoo schema or missing adjusted prices.")
    missing = set(tickers) - set(prices.columns)
    if missing:
        raise DataError(f"No adjusted prices for: {sorted(missing)}.")
    return prices.loc[:, tickers]


def fetch_yahoo(config: Config, cache_dir: Path, refresh: bool = False,
                downloader=None, max_attempts: int = 3) -> DataBundle:
    """Fetch adjusted close explicitly; do not add dividends to these returns again.

    An injected downloader supports deterministic provider-contract tests. The cache
    is intentionally a frozen snapshot until refresh=True; metadata exposes its age.
    """
    query = {"source": "yahoo", "field": "Adj Close", "tickers": config.tickers,
             "start": config.start, "end_exclusive": config.end}
    if not refresh:
        cached = _load_cache(cache_dir, query)
        if cached is not None:
            return cached
    if downloader is None:
        try:
            import yfinance as yf
        except ImportError:
            raise DataError("Yahoo mode requires yfinance. Install requirements-live.txt.") from None
        downloader = yf.download
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive.")
    last_type = "unknown"
    for attempt in range(max_attempts):
        try:
            raw = downloader(config.tickers, start=config.start, end=config.end,
                             auto_adjust=False, actions=True, progress=False,
                             threads=False, group_by="column", timeout=20)
            prices = extract_adjusted_close(raw, config.tickers)
            if prices.notna().sum().min() == 0:
                raise DataError("One or more ticker downloads contain no observations.")
            bundle = DataBundle(prices, {
                **query, "synthetic": False, "retrieved_at_utc": utc_now(),
                "cache_hit": False, "adjustment": "Yahoo adjusted close; no added dividends",
            })
            _save_cache(cache_dir, query, bundle)
            return bundle
        except Exception as exc:
            # A retry is bounded and never substitutes fabricated prices.
            last_type = type(exc).__name__
            LOG.warning("Yahoo attempt %s/%s failed (%s).", attempt + 1, max_attempts, last_type)
            if attempt + 1 < max_attempts:
                time.sleep(min(2 ** attempt, 4))
    raise DataError(
        f"Yahoo failed after {max_attempts} attempts ({last_type}). "
        "Check provider access, tickers, or use an explicit cached CSV/demo mode."
    )


def generate_demo(config: Config) -> DataBundle:
    """Deterministic synthetic total-return indices. These are NOT ETF histories."""
    dates = pd.bdate_range(config.start, pd.Timestamp(config.end) - pd.Timedelta(days=1))
    if len(dates) < config.min_observations:
        raise DataError("Demo date range is too short.")
    rng = np.random.default_rng(config.seed)
    # Common equity, duration, and gold factors; residuals preserve diversification.
    mapping = {
        "SPY": [0.15, 0.00, 0.00], "VEA": [0.14, 0.00, 0.00],
        "VWO": [0.17, 0.00, 0.00], "AGG": [0.01, 0.045, 0.00],
        "IEF": [-0.01, 0.065, 0.00], "TIP": [0.02, 0.04, 0.01],
        "GLD": [0.01, 0.01, 0.13], "VNQ": [0.13, 0.03, 0.00],
    }
    count = len(dates) - 1
    factors = rng.standard_t(7, size=(count, 3)) / np.sqrt(7 / 5)
    factors /= np.sqrt(252)
    factors[int(count * .43):int(count * .46), 0] -= .008
    factors[int(count * .72):int(count * .77), :2] -= .004
    values = {}
    for ticker in config.tickers:
        exposure = np.array(mapping.get(ticker, [.10, .03, .02]))
        drift = .055 if exposure[0] > .1 else .025
        log_returns = drift / 252 + factors @ exposure
        log_returns += rng.normal(0, .04 / np.sqrt(252), size=count)
        values[ticker] = 100 * np.exp(np.r_[0.0, np.cumsum(log_returns)])
    return DataBundle(pd.DataFrame(values, index=dates), {
        "source": "synthetic demo", "synthetic": True, "seed": config.seed,
        "generated_at_utc": utc_now(),
        "description": "Generated total-return indices; ticker labels are illustrative.",
        "calendar": "Weekdays only; exchange holidays are not modeled.",
    })


def load_csv(path: Path) -> DataBundle:
    """CSV contract: Date column followed by USD adjusted total-return price columns."""
    if not path.is_file():
        raise DataError(f"CSV does not exist: {path}")
    try:
        prices = pd.read_csv(path, index_col="Date", parse_dates=True)
    except (ValueError, OSError) as exc:
        raise DataError("CSV needs a Date column and one numeric column per ticker.") from exc
    return DataBundle(prices, {"source": "user CSV", "synthetic": False,
                              "file_name": path.name,
                              "sha256": sha256(path.read_bytes()).hexdigest(),
                              "adjustment": "User-declared adjusted total-return prices"})


def clean_prices(raw: pd.DataFrame, config: Config) -> tuple[pd.DataFrame, dict]:
    """Trim to common history; never forward-fill prices or turn missing data into 0% returns."""
    if raw.empty or raw.columns.duplicated().any():
        raise DataError("Prices are empty or contain duplicate columns.")
    missing = set(config.tickers) - set(raw.columns)
    if missing:
        raise DataError(f"Missing required symbols: {sorted(missing)}.")
    prices = raw.loc[:, config.tickers].copy()
    try:
        index = pd.DatetimeIndex(pd.to_datetime(prices.index, errors="raise"))
    except (ValueError, TypeError):
        raise DataError("Invalid price timestamps.") from None
    if index.hasnans:
        raise DataError("Price timestamps contain NaT.")
    if index.tz is not None:
        index = index.tz_localize(None)  # Preserve exchange-local daily labels.
    prices.index = index.normalize()
    if prices.index.duplicated().any():
        raise DataError("Duplicate dates are ambiguous; resolve them in the source.")
    prices = prices.sort_index()
    prices = prices.loc[(prices.index >= pd.Timestamp(config.start)) &
                        (prices.index < pd.Timestamp(config.end))]
    if prices.empty:
        raise DataError("No prices in the configured interval.")
    try:
        prices = prices.apply(pd.to_numeric, errors="raise")
    except (ValueError, TypeError):
        raise DataError("Prices contain nonnumeric values.") from None
    array = prices.to_numpy(dtype=float)
    if np.isinf(array).any() or ((array <= 0) & ~np.isnan(array)).any():
        raise DataError("Observed prices must be finite and strictly positive.")
    if prices.notna().sum().min() == 0:
        raise DataError("A required asset has no valid history.")
    first = max(prices[c].first_valid_index() for c in prices)
    last = min(prices[c].last_valid_index() for c in prices)
    original_count = len(prices)
    prices = prices.loc[first:last]
    if len(prices) < config.min_observations:
        raise DataError(f"Need at least {config.min_observations} common price observations.")
    if prices.isna().any().any():
        cells = prices.isna().stack()
        example = [str(x) for x in cells[cells].index[:5]]
        raise DataError(f"Interior price gaps are not imputed. Example cells: {example}")
    largest_gap = int(prices.index.to_series().diff().dt.days.max())
    if largest_gap > 7:
        raise DataError(f"A {largest_gap}-day calendar gap needs investigation.")
    returns = prices.pct_change(fill_method=None).iloc[1:]
    extremes = returns.abs().gt(.35)
    warnings = []
    if original_count != len(prices):
        warnings.append(f"Trimmed {original_count - len(prices)} rows to common asset history.")
    if extremes.any().any():
        warnings.append(f"{int(extremes.sum().sum())} daily moves exceed 35%; inspect adjustment quality.")
    # Record, rather than hide, stale tails relative to the requested end.
    tail_days = (pd.Timestamp(config.end) - prices.index[-1]).days
    if tail_days > 7:
        warnings.append(f"Data ends {tail_days} days before the requested exclusive end.")
    audit = {
        "rows": len(prices), "return_observations": len(prices) - 1,
        "assets": len(prices.columns), "first_date": str(prices.index[0].date()),
        "last_date": str(prices.index[-1].date()), "trimmed_rows": original_count - len(prices),
        "interior_missing_cells": 0, "largest_calendar_gap_days": largest_gap,
        "warnings": warnings,
        "calendar_policy": "Observed common sessions; no exchange-calendar reconstruction.",
    }
    return prices.astype(float), audit


def fetch_fred_yields(config: Config, api_key: str, cache_dir: Path,
                      refresh: bool = False) -> DataBundle:
    """DGS3MO annual yields in percent; API credentials are never stored or logged."""
    if not api_key:
        raise DataError("FRED mode requires FRED_API_KEY in your environment/Colab secrets.")
    start = (pd.Timestamp(config.start) - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    query = {"source": "FRED", "series": "DGS3MO", "start": start, "end": config.end}
    if not refresh:
        cached = _load_cache(cache_dir, query)
        if cached is not None:
            return cached
    params = {"series_id": "DGS3MO", "api_key": api_key, "file_type": "json",
              "observation_start": start, "observation_end": config.end}
    url = "https://api.stlouisfed.org/fred/series/observations?" + urlencode(params)
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "PortfolioLab/1.0"})
            with urlopen(request, timeout=25) as response:
                content = json.load(response)
            observations = content["observations"]
            frame = pd.DataFrame(observations)
            frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
            prices = frame.set_index(pd.to_datetime(frame["date"]))[["value"]].dropna()
            prices.columns = ["DGS3MO"]
            if prices.empty:
                raise DataError("FRED returned no valid rates.")
            bundle = DataBundle(prices, {
                **query, "units": "percent per annum, investment basis",
                "retrieved_at_utc": utc_now(), "cache_hit": False,
                "vintage": "latest available; not a point-in-time ALFRED reconstruction",
            })
            _save_cache(cache_dir, query, bundle)
            return bundle
        except HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code != 429:
                raise DataError(f"FRED request rejected (HTTP {exc.code}); check credentials.") from None
        except (URLError, TimeoutError, ValueError, KeyError):
            pass
        if attempt < 2:
            time.sleep(2 ** attempt)
    raise DataError("FRED request failed. No constant-rate fallback was applied.") from None


def risk_free_returns(index: pd.DatetimeIndex, annual_rate: float = .02,
                      yields_percent: pd.Series | None = None) -> tuple[pd.Series, dict]:
    """Cash-return proxy over each close-to-close calendar interval.

    The fixed rate is effective annual. For FRED, treating a quoted Treasury yield
    as effective annual is an approximation, not the realized return of a bill.
    A FRED quote must predate the START of the interval (strict backward as-of).
    """
    index = pd.DatetimeIndex(index)
    if len(index) < 2 or index.has_duplicates or not index.is_monotonic_increasing:
        raise DataError("Risk-free dates must be increasing, unique, and contain two observations.")
    days = np.diff(index.values).astype("timedelta64[D]").astype(float)
    if yields_percent is None:
        if not np.isfinite(annual_rate) or annual_rate <= -1:
            raise DataError("Invalid fixed annual risk-free assumption.")
        rates = np.full(len(days), annual_rate)
        metadata = {"source": "fixed assumption", "annual_effective_rate": annual_rate}
    else:
        quotes = yields_percent.dropna().sort_index()
        if quotes.empty or quotes.index.has_duplicates:
            raise DataError("FRED yields are empty or contain duplicate dates.")
        loc = quotes.index.searchsorted(index[:-1], side="left") - 1
        if (loc < 0).any():
            raise DataError("No risk-free quote predates the first return interval.")
        ages = (index[:-1] - quotes.index[loc]).days
        if (ages > 10).any():
            raise DataError("Risk-free observations are stale by more than 10 calendar days.")
        rates = quotes.iloc[loc].to_numpy(dtype=float) / 100
        if not np.isfinite(rates).all() or (rates <= -1).any():
            raise DataError("Risk-free annualized yields are invalid.")
        metadata = {"source": "FRED DGS3MO proxy", "max_quote_age_days": int(max(ages)),
                    "method": "strictly prior quote; effective-annual approximation; actual/365.25"}
    values = np.expm1(np.log1p(rates) * days / 365.25)
    return pd.Series(values, index=index[1:], name="risk_free_return"), metadata
