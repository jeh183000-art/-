"""Causal feature groups for BTCUSDT next-four-hour candle classification.

API
---
``X_by_group, meta = build_features(btc4h, btc15m, eth4h)``

Inputs are ascending, duplicate-free Binance trade-price candles with integer
UTC millisecond open/close timestamps. The caller must use only closed BTC 4h
candles when making an actual forecast. Inputs are copied and never changed.

* G1: the exact 38 features and eligibility rule from the frozen 4h V1.
* G2: G1 plus causal 4h shape, trend, volatility, and flow measurements.
* G3: G2 plus measurements inside the current completed 4h bucket. A bucket
  must contain all sixteen 15m candles; partial buckets are ineligible.
* G4: G3 plus exactly aligned ETH 4h context. There is no forward filling.

The returned frames share the original BTC row index after resetting it.
``meta.eligible_G1`` through ``eligible_G4`` are group-specific masks. ``y``
and all forward target information exist only in meta. Undefined ratios stay
NaN for a training-only imputer; they are never filled using later values.
No estimator is fitted here, and this module never reads files on import.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BAR_MS = 14_400_000
INTRA_MS = 900_000
WARMUP = 96
GROUPS = ("G1", "G2", "G3", "G4")
REQUIRED = ("open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_volume")

INTRABAR_COLUMNS = (
    "intra_return_full", "intra_return_last_1", "intra_return_last_2",
    "intra_return_last_4", "intra_return_last_8", "intra_return_first_8",
    "intra_return_last8_minus_first8", "intra_up_fraction_16",
    "intra_up_fraction_last4", "intra_realized_variance",
    "intra_downside_semivariance", "intra_upside_semivariance",
    "intra_max_drawdown_closes", "intra_taker_fraction_16",
    "intra_taker_fraction_last4", "intra_taker_fraction_first4",
    "intra_taker_last4_minus_first4", "intra_volume_share_last4",
    "intra_volume_share_maxbar", "intra_slope_normalized_rv",
    "intra_close_location", "intra_last_body_pct", "intra_last_range_pct",
    "intra_path_efficiency", "intra_volume_last4_to_first4",
    "intra_zero_volume_fraction", "intra_taker_last4_missing",
)
ETH_COLUMNS = (
    "eth_return_1", "eth_return_4", "eth_return_16",
    "relative_return_1", "relative_return_4", "relative_return_16",
    "eth_body_pct", "eth_range_pct", "eth_return_std_16",
    "btc_to_eth_volatility_16", "eth_volume_ratio_16",
    "relative_volume_ratio_16", "relative_log_price_z48",
    "btc_eth_return_correlation_48", "eth_taker_fraction_16",
    "relative_taker_fraction_4", "relative_up_fraction_16",
    "eth_body_lag_1",
)


def _ratio(numerator, denominator):
    """Division retaining missing/undefined ratios, never imputing values."""
    if isinstance(denominator, pd.Series):
        return numerator / denominator.replace(0, np.nan)
    num = np.asarray(numerator, dtype=float)
    den = np.asarray(denominator, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = num / den
    return np.where(np.isfinite(out) & (den != 0), out, np.nan)


def validate_bars(frame: pd.DataFrame, interval_ms: int = BAR_MS) -> pd.DataFrame:
    """Validate data without sorting, deduplicating, filling, or repairing it."""
    missing = set(REQUIRED) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required candle columns: {sorted(missing)}")
    bars = frame.copy().reset_index(drop=True)
    for name in REQUIRED:
        bars[name] = pd.to_numeric(bars[name], errors="raise")
    if bars.empty or not np.isfinite(bars[list(REQUIRED)].to_numpy()).all():
        raise ValueError("Empty input or non-finite candle value")
    for name in ("open_time", "close_time"):
        if not np.equal(bars[name], np.floor(bars[name])).all():
            raise ValueError("Timestamps must be integer UTC milliseconds")
        bars[name] = bars[name].astype("int64")
    if not bars.open_time.is_monotonic_increasing or bars.open_time.duplicated().any():
        raise ValueError("Candles must be strictly ascending with no duplicates")
    if (bars.open_time % interval_ms != 0).any():
        raise ValueError("Candle open is not on the required UTC grid")
    if (bars.close_time != bars.open_time + interval_ms - 1).any():
        raise ValueError("Unexpected candle close timestamp")
    if (bars[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    if ((bars.high < bars[["open", "close", "low"]].max(axis=1)) |
            (bars.low > bars[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("Invalid OHLC bounds")
    if (bars[["volume", "quote_volume", "trades", "taker_buy_volume"]] < 0).any().any():
        raise ValueError("Volume and trade counts cannot be negative")
    if (bars.taker_buy_volume > bars.volume + 1e-7).any():
        raise ValueError("Taker buy volume exceeds volume")
    return bars


def _history_count(bars: pd.DataFrame) -> pd.Series:
    segments = bars.open_time.diff().ne(BAR_MS).cumsum()
    return bars.groupby(segments, sort=False).cumcount()


def baseline_features(bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Exact frozen V1 arithmetic, feature names, ordering, and eligibility."""
    close, opening, high, low = (bars[c] for c in ("close", "open", "high", "low"))
    ret = close.pct_change(fill_method=None)
    body = (close - opening) / opening
    span = high - low
    features: dict[str, pd.Series | np.ndarray] = {}
    for lookback in (1, 2, 3, 4, 8, 16, 32, 96):
        features[f"return_{lookback}"] = close.pct_change(lookback, fill_method=None)
    features.update({
        "signed_body_pct": body,
        "range_pct": span / opening,
        "upper_wick_pct": (high - pd.concat([opening, close], axis=1).max(axis=1)) / opening,
        "lower_wick_pct": (pd.concat([opening, close], axis=1).min(axis=1) - low) / opening,
        "close_location": ((close - low) / span.replace(0, np.nan)).fillna(0.5),
    })
    for lag in (1, 2, 3, 4):
        features[f"body_lag_{lag}"] = body.shift(lag)
    for window in (4, 16, 96):
        features[f"return_std_{window}"] = ret.rolling(window).std(ddof=0)
    for window in (4, 16, 48, 96):
        features[f"close_to_sma_{window}"] = close / close.rolling(window).mean() - 1
    for window in (4, 16):
        features[f"up_fraction_{window}"] = (close > opening).astype(float).rolling(window).mean()
    for window in (4, 16, 96):
        features[f"volume_ratio_{window}"] = bars.volume / bars.volume.rolling(window).mean()
    for column in ("quote_volume", "trades"):
        features[f"{column}_ratio_16"] = bars[column] / bars[column].rolling(16).mean()
    for window in (1, 4, 16):
        features[f"taker_buy_fraction_{window}"] = (
            bars.taker_buy_volume.rolling(window).sum() / bars.volume.rolling(window).sum()
        )
    prediction_datetime = pd.to_datetime(bars.close_time + 1, unit="ms", utc=True)
    hour = prediction_datetime.dt.hour + prediction_datetime.dt.minute / 60
    weekday = prediction_datetime.dt.dayofweek
    features["utc_hour_sin"] = np.sin(2 * np.pi * hour / 24)
    features["utc_hour_cos"] = np.cos(2 * np.pi * hour / 24)
    features["utc_weekday_sin"] = np.sin(2 * np.pi * weekday / 7)
    features["utc_weekday_cos"] = np.cos(2 * np.pi * weekday / 7)
    X = pd.DataFrame(features, index=bars.index).replace([np.inf, -np.inf], np.nan)
    assert X.shape[1] == 38
    eligible = (_history_count(bars) >= WARMUP) & X.notna().all(axis=1)
    return X, eligible


def _rich_features(bars: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    opening, high, low, close = (bars[c] for c in ("open", "high", "low", "close"))
    body = (close - opening) / opening
    ret = close.pct_change(fill_method=None)
    span = high - low
    upper = high - pd.concat([opening, close], axis=1).max(axis=1)
    lower = pd.concat([opening, close], axis=1).min(axis=1) - low
    extra = {}
    for lag in (5, 6, 7, 8):
        extra[f"body_lag_{lag}"] = body.shift(lag)
    extra["signed_body_to_range"] = _ratio(close - opening, span)
    extra["upper_wick_to_range"] = _ratio(upper, span)
    extra["lower_wick_to_range"] = _ratio(lower, span)
    extra["wick_balance_to_range"] = _ratio(upper - lower, span)
    extra["body_magnitude_to_mean16"] = _ratio(body.abs(), body.abs().rolling(16).mean())
    for lag, window in ((1, 16), (4, 16), (16, 96)):
        extra[f"return_{lag}_normalized_vol{window}"] = _ratio(
            baseline[f"return_{lag}"], baseline[f"return_std_{window}"] * np.sqrt(lag))
    previous_close = close.shift(1)
    true_range = pd.concat([span, (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
    atr14 = true_range.rolling(14).mean()
    extra["atr14_pct"] = atr14 / opening
    extra["range_to_atr14"] = _ratio(span, atr14)
    for window in (4, 16, 96):
        rolling_high = high.rolling(window).max()
        rolling_low = low.rolling(window).min()
        extra[f"distance_to_high_{window}"] = close / rolling_high - 1
        extra[f"distance_to_low_{window}"] = close / rolling_low - 1
        extra[f"range_location_{window}"] = _ratio(close - rolling_low, rolling_high - rolling_low)
    color = np.sign(close - opening)
    streak_start = color.ne(color.shift(1)) | bars.open_time.diff().ne(BAR_MS) | color.eq(0)
    streak_count = bars.groupby(streak_start.cumsum(), sort=False).cumcount() + 1
    extra["signed_color_streak_capped96"] = color * streak_count.clip(upper=96)
    for short, long in ((4, 16), (16, 96), (4, 96)):
        extra[f"volatility_ratio_{short}_{long}"] = _ratio(
            baseline[f"return_std_{short}"], baseline[f"return_std_{long}"])
    delta = close.diff()
    gains = delta.clip(lower=0).rolling(14).sum()
    losses = (-delta.clip(upper=0)).rolling(14).sum()
    extra["rsi14_fraction"] = _ratio(gains, gains + losses)
    imbalance = 2 * baseline["taker_buy_fraction_1"] - 1
    extra["taker_imbalance"] = imbalance
    extra["taker_imbalance_lag1"] = imbalance.shift(1)
    extra["taker_imbalance_lag2"] = imbalance.shift(2)
    extra["taker_imbalance_4"] = 2 * baseline["taker_buy_fraction_4"] - 1
    extra["taker_imbalance_16"] = 2 * baseline["taker_buy_fraction_16"] - 1
    extra["taker_fraction_change_vs16"] = baseline["taker_buy_fraction_1"] - baseline["taker_buy_fraction_16"]
    extra["taker_return_correlation16"] = imbalance.rolling(16).corr(ret)
    for window in (16, 48):
        extra[f"return_autocorrelation1_{window}"] = ret.rolling(window).corr(ret.shift(1))
    for window in (4, 16):
        extra[f"range_pct_to_mean_{window}"] = _ratio(baseline.range_pct, baseline.range_pct.rolling(window).mean())
    return pd.DataFrame(extra, index=bars.index).replace([np.inf, -np.inf], np.nan)


def intrabar_features(bars15m: pd.DataFrame) -> pd.DataFrame:
    """One row per exact completed sixteen-candle UTC 4h bucket, vectorized."""
    bars = validate_bars(bars15m, INTRA_MS)
    bucket = bars.open_time // BAR_MS * BAR_MS
    counts = bars.groupby(bucket, sort=True).size()
    complete_buckets = counts[counts.eq(16)].index.to_numpy(dtype="int64")
    good = bars.loc[bucket.isin(complete_buckets)].copy()
    if not len(good):
        return pd.DataFrame(columns=INTRABAR_COLUMNS, index=pd.Index([], name="open_time", dtype="int64"), dtype=float)
    values = {name: good[name].to_numpy(dtype=float).reshape(-1, 16)
              for name in ("open", "high", "low", "close", "volume", "taker_buy_volume")}
    times = good.open_time.to_numpy(dtype="int64").reshape(-1, 16)
    ends = good.close_time.to_numpy(dtype="int64").reshape(-1, 16)
    expected = complete_buckets[:, None] + np.arange(16)[None, :] * INTRA_MS
    if not np.array_equal(times, expected) or not np.array_equal(ends[:, -1] + 1, complete_buckets + BAR_MS):
        raise ValueError("Sixteen intrabar rows do not form a complete UTC 4h bucket")
    opening, high, low, close, volume, buys = (values[name] for name in ("open", "high", "low", "close", "volume", "taker_buy_volume"))
    log_close = np.log(close)
    increments = np.diff(np.concatenate([np.log(opening[:, [0]]), log_close], axis=1), axis=1)
    rv = (increments ** 2).sum(axis=1)
    total_volume = volume.sum(axis=1)
    first4_volume = volume[:, :4].sum(axis=1)
    last4_volume = volume[:, -4:].sum(axis=1)
    first4_fraction = _ratio(buys[:, :4].sum(axis=1), first4_volume)
    last4_fraction = _ratio(buys[:, -4:].sum(axis=1), last4_volume)
    first8_return = close[:, 7] / opening[:, 0] - 1
    last8_return = close[:, -1] / opening[:, -8] - 1
    x = np.arange(16, dtype=float) - 7.5
    slope = (log_close * x[None, :]).sum(axis=1) / np.square(x).sum()
    running_high_close = np.maximum.accumulate(close, axis=1)
    columns = {"intra_return_full": close[:, -1] / opening[:, 0] - 1}
    for n in (1, 2, 4, 8):
        columns[f"intra_return_last_{n}"] = close[:, -1] / opening[:, -n] - 1
    columns.update({
        "intra_return_first_8": first8_return,
        "intra_return_last8_minus_first8": last8_return - first8_return,
        "intra_up_fraction_16": (close > opening).mean(axis=1),
        "intra_up_fraction_last4": (close[:, -4:] > opening[:, -4:]).mean(axis=1),
        "intra_realized_variance": rv,
        "intra_downside_semivariance": np.square(np.minimum(increments, 0)).sum(axis=1),
        "intra_upside_semivariance": np.square(np.maximum(increments, 0)).sum(axis=1),
        "intra_max_drawdown_closes": (close / running_high_close - 1).min(axis=1),
        "intra_taker_fraction_16": _ratio(buys.sum(axis=1), total_volume),
        "intra_taker_fraction_last4": last4_fraction,
        "intra_taker_fraction_first4": first4_fraction,
        "intra_taker_last4_minus_first4": last4_fraction - first4_fraction,
        "intra_volume_share_last4": _ratio(last4_volume, total_volume),
        "intra_volume_share_maxbar": _ratio(volume.max(axis=1), total_volume),
        "intra_slope_normalized_rv": _ratio(slope, np.sqrt(rv / 16)),
        "intra_close_location": _ratio(close[:, -1] - low.min(axis=1), high.max(axis=1) - low.min(axis=1)),
        "intra_last_body_pct": close[:, -1] / opening[:, -1] - 1,
        "intra_last_range_pct": (high[:, -1] - low[:, -1]) / opening[:, -1],
        "intra_path_efficiency": _ratio(log_close[:, -1] - np.log(opening[:, 0]), np.abs(increments).sum(axis=1)),
        "intra_volume_last4_to_first4": _ratio(last4_volume, first4_volume),
        "intra_zero_volume_fraction": (volume == 0).mean(axis=1),
        "intra_taker_last4_missing": (last4_volume == 0).astype(float),
    })
    frame = pd.DataFrame(columns, index=pd.Index(complete_buckets, name="open_time"))
    return frame.loc[:, list(INTRABAR_COLUMNS)].replace([np.inf, -np.inf], np.nan)


def _eth_features(btc: pd.DataFrame, baseline: pd.DataFrame,
                  eth: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    e = validate_bars(eth, BAR_MS)
    eth_history = (_history_count(e) >= WARMUP).to_numpy()
    btc_index = pd.Index(btc.open_time, name="open_time")
    # Compute ETH rolling features on its original time axis, then exact-join.
    base = pd.DataFrame(index=pd.Index(e.open_time, name="open_time"))
    for n in (1, 4, 16):
        base[f"eth_return_{n}"] = e.close.pct_change(n, fill_method=None).to_numpy()
    base["eth_body_pct"] = ((e.close - e.open) / e.open).to_numpy()
    base["eth_range_pct"] = ((e.high - e.low) / e.open).to_numpy()
    base["eth_return_std_16"] = e.close.pct_change(fill_method=None).rolling(16).std(ddof=0).to_numpy()
    base["eth_volume_ratio_16"] = _ratio(e.volume, e.volume.rolling(16).mean()).to_numpy()
    base["eth_taker_fraction_16"] = _ratio(e.taker_buy_volume.rolling(16).sum(), e.volume.rolling(16).sum()).to_numpy()
    base["eth_taker_fraction_4_internal"] = _ratio(e.taker_buy_volume.rolling(4).sum(), e.volume.rolling(4).sum()).to_numpy()
    base["eth_up_fraction16_internal"] = (e.close > e.open).astype(float).rolling(16).mean().to_numpy()
    base["eth_body_lag_1"] = ((e.close - e.open) / e.open).shift(1).to_numpy()
    base["eth_close_internal"] = e.close.to_numpy()
    base["eth_closed_at_internal"] = (e.close_time + 1).to_numpy()
    base["eth_history_internal"] = eth_history
    aligned = base.reindex(btc_index).reset_index(drop=True)
    available = aligned.eth_closed_at_internal.eq(btc.close_time + 1) & aligned.eth_history_internal.eq(True)
    extra = {}
    for n in (1, 4, 16):
        extra[f"eth_return_{n}"] = aligned[f"eth_return_{n}"]
        extra[f"relative_return_{n}"] = baseline[f"return_{n}"] - aligned[f"eth_return_{n}"]
    for name in ("eth_body_pct", "eth_range_pct", "eth_return_std_16", "eth_volume_ratio_16",
                 "eth_taker_fraction_16", "eth_body_lag_1"):
        extra[name] = aligned[name]
    extra["btc_to_eth_volatility_16"] = _ratio(baseline.return_std_16, aligned.eth_return_std_16)
    extra["relative_volume_ratio_16"] = _ratio(baseline.volume_ratio_16, aligned.eth_volume_ratio_16)
    log_ratio = np.log(btc.close / aligned.eth_close_internal)
    extra["relative_log_price_z48"] = _ratio(log_ratio - log_ratio.rolling(48).mean(), log_ratio.rolling(48).std(ddof=0))
    extra["btc_eth_return_correlation_48"] = baseline.return_1.rolling(48).corr(aligned.eth_return_1)
    extra["relative_taker_fraction_4"] = baseline.taker_buy_fraction_4 - aligned.eth_taker_fraction_4_internal
    extra["relative_up_fraction_16"] = baseline.up_fraction_16 - aligned.eth_up_fraction16_internal
    frame = pd.DataFrame(extra, index=btc.index).reindex(columns=list(ETH_COLUMNS))
    return frame.replace([np.inf, -np.inf], np.nan), available


def build_features(btc4h: pd.DataFrame, btc15m: pd.DataFrame | None = None,
                   eth4h: pd.DataFrame | None = None) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Build all fixed feature groups and separately aligned next-candle labels."""
    btc = validate_bars(btc4h, BAR_MS)
    G1, eligible = baseline_features(btc)
    G2 = pd.concat([G1, _rich_features(btc, G1)], axis=1)
    if btc15m is None:
        intra = pd.DataFrame(np.nan, index=btc.index, columns=list(INTRABAR_COLUMNS))
        complete = pd.Series(False, index=btc.index)
    else:
        buckets = intrabar_features(btc15m)
        complete = pd.Series(btc.open_time.isin(buckets.index).to_numpy(), index=btc.index)
        intra = buckets.reindex(pd.Index(btc.open_time, name="open_time")).reset_index(drop=True)
    G3 = pd.concat([G2, intra], axis=1)
    if eth4h is None:
        eth_features = pd.DataFrame(np.nan, index=btc.index, columns=list(ETH_COLUMNS))
        eth_available = pd.Series(False, index=btc.index)
    else:
        eth_features, eth_available = _eth_features(btc, G1, eth4h)
    G4 = pd.concat([G3, eth_features], axis=1)
    X = {"G1": G1, "G2": G2, "G3": G3, "G4": G4}
    for name, frame in X.items():
        if frame.columns.duplicated().any() or frame.shape[1] >= 200:
            raise ValueError(f"Invalid feature schema for {name}")
    next_open = btc.open.shift(-1)
    next_close = btc.close.shift(-1)
    contiguous = btc.open_time.shift(-1).eq(btc.open_time + BAR_MS)
    color = np.sign(next_close - next_open).where(contiguous)
    y = ((color + 1) / 2).where(color.ne(0))
    meta = pd.DataFrame({
        "current_open_time": btc.open_time,
        "prediction_time": btc.close_time + 1,
        "target_open_time": btc.open_time + BAR_MS,
        "target_close_time": btc.open_time + 2 * BAR_MS - 1,
        "label_end_time": btc.open_time + 2 * BAR_MS,
        "current_color": np.sign(btc.close - btc.open),
        "target_color": color,
        "target_available": contiguous,
        "y": y,
        "feature_eligible": eligible,
        "eligible_G1": eligible,
        "eligible_G2": eligible,
        "eligible_G3": eligible & complete,
        "eligible_G4": eligible & complete & eth_available,
        "intrabar_complete": complete,
        "eth_available": eth_available,
        "target_open": next_open.where(contiguous),
        "target_close": next_close.where(contiguous),
    })
    return X, meta


def feature_schema() -> dict:
    """Descriptive fixed protocol constants, without reading data or fitting."""
    return {"bar_ms": BAR_MS, "intrabar_ms": INTRA_MS, "warmup_bars": WARMUP,
            "groups": {"G1": "Frozen V1 38", "G2": "G1 plus 4h shape/regime",
                       "G3": "G2 plus completed current-bucket 15m flow",
                       "G4": "G3 plus exact-joined ETH 4h context"},
            "imputation": "None here; undefined ratios remain NaN for train-only imputer",
            "ETH_alignment": "Exact open/close timestamp; no forward fill; 96 contiguous prior bars",
            "intrabar_alignment": "Exactly sixteen contiguous UTC-aligned 15m constituents"}
