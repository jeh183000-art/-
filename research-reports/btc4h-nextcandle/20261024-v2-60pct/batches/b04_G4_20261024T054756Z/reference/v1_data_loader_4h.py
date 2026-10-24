#!/usr/bin/env python3
"""Download official Binance USD-M BTCUSDT 4h archives and audit, never fill gaps.

Usage: python data_loader.py --start 2022-01 --end 2025-12
Only public, unauthenticated Binance archive URLs are accessed.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import zipfile

import numpy as np
import pandas as pd

BASE = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/4h"
COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
STEP_MS = 14_400_000


def fetch(url: str) -> bytes:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401, 403, 404, 418, 451):
                raise
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    raise RuntimeError("unreachable")


def download_month(month: str, raw: Path) -> dict:
    filename = f"BTCUSDT-4h-{month}.zip"
    url = f"{BASE}/{filename}"
    target = raw / filename
    checksum_path = raw / (filename + ".CHECKSUM")
    checksum = checksum_path.read_bytes() if checksum_path.exists() else fetch(url + ".CHECKSUM")
    expected = checksum.decode("utf-8").strip().split()[0]
    blob = target.read_bytes() if target.exists() else fetch(url)
    actual = hashlib.sha256(blob).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA256 mismatch {filename}: {actual} != {expected}")
    target.write_bytes(blob)
    checksum_path.write_bytes(checksum)
    return {"month": month, "url": url, "file": filename, "bytes": len(blob), "sha256": actual, "checksum_verified": True}


def read_month(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != 1 or not names[0].endswith(".csv"):
            raise ValueError(f"Unexpected archive contents: {path.name}")
        blob = archive.read(names[0])
    frame = pd.read_csv(io.BytesIO(blob), header=None, dtype=str)
    if len(frame.columns) != len(COLUMNS):
        raise ValueError(f"Unexpected column count in {path}")
    if frame.iloc[0, 0] in ("open_time", "open_timestamp"):
        frame = frame.iloc[1:].reset_index(drop=True)
    frame.columns = COLUMNS
    for col in COLUMNS:
        frame[col] = pd.to_numeric(frame[col], errors="raise")
    for col in ("open_time", "close_time", "trades"):
        if not np.all(np.equal(frame[col], np.floor(frame[col]))):
            raise ValueError(f"Noninteger {col} in {path}")
        frame[col] = frame[col].astype("int64")
    # Futures archives are milliseconds; fail rather than guessing another unit.
    if not frame["open_time"].between(1_500_000_000_000, 3_000_000_000_000).all():
        raise ValueError(f"Unexpected timestamp unit in {path}")
    return frame.drop(columns="ignore")


def audit(frame: pd.DataFrame, first_month: str, last_month: str) -> dict:
    start = pd.Timestamp(first_month + "-01", tz="UTC")
    end = pd.Timestamp(last_month + "-01", tz="UTC") + pd.offsets.MonthBegin(1)
    expected = pd.date_range(start, end, freq="4h", inclusive="left")
    times = pd.to_datetime(frame.open_time, unit="ms", utc=True)
    actual = pd.DatetimeIndex(times)
    missing = expected.difference(actual)
    missing_ranges = []
    for stamp in missing:
        if missing_ranges and stamp == missing_ranges[-1][1] + pd.Timedelta(hours=4):
            missing_ranges[-1][1] = stamp
        else:
            missing_ranges.append([stamp, stamp])
    intervals = frame.open_time.diff().dropna()
    invalid_ohlc = ((frame.high < frame[["open", "close", "low"]].max(axis=1)) | (frame.low > frame[["open", "close", "high"]].min(axis=1)) | (frame[["open", "high", "low", "close"]] <= 0).any(axis=1))
    negatives = (frame[["volume", "quote_volume", "trades", "taker_buy_volume", "taker_buy_quote_volume"]] < 0).any(axis=1)
    bad_taker = frame.taker_buy_volume > frame.volume + 1e-7
    return {
        "symbol": "BTCUSDT", "market": "Binance USD-M perpetual", "interval": "4h", "timestamp_unit": "milliseconds", "timezone": "UTC",
        "expected_start": start.isoformat(), "expected_end_exclusive": end.isoformat(),
        "rows": len(frame), "expected_rows": len(expected),
        "first_open": times.iloc[0].isoformat(), "last_open": times.iloc[-1].isoformat(),
        "sorted_ascending": bool(frame.open_time.is_monotonic_increasing),
        "duplicate_open_times": int(frame.open_time.duplicated().sum()),
        "missing_bars": len(missing),
        "missing_ranges": [{"start": a.isoformat(), "end": b.isoformat(), "bars": int((b-a)/pd.Timedelta(hours=4))+1} for a,b in missing_ranges],
        "non_4h_intervals": int((intervals != STEP_MS).sum()),
        "off_grid_bars": int((frame.open_time % STEP_MS != 0).sum()),
        "bad_close_times": int((frame.close_time != frame.open_time + STEP_MS - 1).sum()),
        "outside_requested_range": int(((times < start) | (times >= end)).sum()),
        "invalid_ohlc_rows": int(invalid_ohlc.sum()), "negative_volume_rows": int(negatives.sum()), "invalid_taker_rows": int(bad_taker.sum()),
        "nonfinite_numeric_rows": int((~np.isfinite(frame.to_numpy(dtype=float))).any(axis=1).sum()),
        "doji_bars": int((frame.close == frame.open).sum()),
        "up_bars": int((frame.close > frame.open).sum()), "down_bars": int((frame.close < frame.open).sum()),
        "imputation": "none", "deduplication": "none", "source_order_preserved": True,
    }


def compare_15m(frame: pd.DataFrame, source: Path) -> dict:
    """Validate official 4h bars against 16 original 15m bars; never fill gaps."""
    smaller = pd.read_csv(source)
    if smaller.open_time.duplicated().any() or not smaller.open_time.is_monotonic_increasing:
        raise ValueError("15m reference must have unique increasing open times")
    if (smaller.open_time.diff().dropna() != 900_000).any():
        raise ValueError("15m reference has gaps; no artificial 4h bars may be constructed")
    if (smaller.close_time != smaller.open_time + 900_000 - 1).any():
        raise ValueError("15m reference has invalid close times")
    smaller = smaller.copy()
    smaller['bucket'] = smaller.open_time // STEP_MS * STEP_MS
    grouping = smaller.groupby('bucket', sort=True)
    sizes = grouping.size()
    if not sizes.eq(16).all():
        raise ValueError("Every 4h aggregation bucket must contain exactly 16 source candles")
    aggregated = grouping.agg(open_time=('open_time', 'first'), open=('open', 'first'),
                             high=('high', 'max'), low=('low', 'min'), close=('close', 'last'),
                             volume=('volume', 'sum'), close_time=('close_time', 'last'),
                             quote_volume=('quote_volume', 'sum'), trades=('trades', 'sum'),
                             taker_buy_volume=('taker_buy_volume', 'sum'),
                             taker_buy_quote_volume=('taker_buy_quote_volume', 'sum'))
    if not np.array_equal(aggregated.open_time.to_numpy(), frame.open_time.to_numpy()):
        raise ValueError("Official 4h timestamps differ from 15m aggregation timestamps")
    findings = []
    mismatched_indices = set()
    detail = []
    for column in frame.columns:
        actual = frame[column].to_numpy()
        expected = aggregated[column].to_numpy()
        integer_or_ohlc = column in ('open_time', 'close_time', 'trades', 'open', 'high', 'low', 'close')
        rtol, atol = (0.0, 0.0) if integer_or_ohlc else (1e-12, 1e-7)
        difference = np.abs(actual - expected)
        equal = np.isclose(actual, expected, rtol=rtol, atol=atol)
        findings.append({'column': column, 'max_absolute_difference': float(difference.max()),
                         'mismatched_rows': int((~equal).sum()), 'rtol': rtol, 'atol': atol})
        for index in np.flatnonzero(~equal):
            mismatched_indices.add(int(index))
            detail.append({'open_time': int(frame.open_time.iloc[index]),
                           'open_utc': pd.Timestamp(int(frame.open_time.iloc[index]), unit='ms', tz='UTC').isoformat(),
                           'column': column, 'official_4h': float(actual[index]),
                           'aggregated_15m': float(expected[index]),
                           'official_minus_aggregate': float(actual[index]-expected[index]),
                           'relative_difference_vs_official': float((actual[index]-expected[index])/actual[index]) if actual[index] else None})
    official_colors = np.sign(frame.close.to_numpy()-frame.open.to_numpy())
    aggregate_colors = np.sign(aggregated.close.to_numpy()-aggregated.open.to_numpy())
    windows = []
    for index in sorted(mismatched_indices):
        stamp = int(frame.open_time.iloc[index])
        components = smaller[smaller.bucket.eq(stamp)]
        windows.append({'open_time': stamp, 'open_utc': pd.Timestamp(stamp,unit='ms',tz='UTC').isoformat(),
                        'official_open': float(frame.open.iloc[index]),
                        'aggregated_open': float(aggregated.open.iloc[index]),
                        'official_close': float(frame.close.iloc[index]),
                        'aggregated_close': float(aggregated.close.iloc[index]),
                        'official_target_color': int(official_colors[index]),
                        'aggregated_target_color': int(aggregate_colors[index]),
                        'target_label_changed': bool(official_colors[index]!=aggregate_colors[index]),
                        'zero_volume_15m_components': int(components.volume.eq(0).sum()),
                        'official_volume': float(frame.volume.iloc[index]),
                        'aggregated_volume': float(aggregated.volume.iloc[index]),
                        'relative_volume_shortfall_vs_official': float((frame.volume.iloc[index]-aggregated.volume.iloc[index])/frame.volume.iloc[index])})
    report = {'status': 'PASS' if not any(x['mismatched_rows'] for x in findings) else 'FAIL',
              'reference_15m_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'reference_15m_rows': len(smaller), 'official_4h_rows': len(frame),
              'aggregation': 'UTC start-of-day anchored 4h; each bucket has exactly 16 contiguous 15m bars',
              'component_count_min': int(sizes.min()), 'component_count_max': int(sizes.max()),
              'imputation': 'none', 'fields': findings,
              'mismatched_windows_count': len(windows), 'mismatched_windows': windows,
              'all_8766_target_color_mismatches': int((official_colors!=aggregate_colors).sum()),
              'field_discrepancies': detail,
              'interpretation': 'Exact cross-timeframe equality fails; official4h raw input passes its own structural and checksum audit. Differences are recorded without repair or imputation. Source discrepancy cause is not established.',
              'canonical_input': 'Official 4h monthly archives, selected before model fitting; 15m aggregation is diagnostic only.'}
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2022-01")
    parser.add_argument("--end", default="2025-12")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--compare-15m", type=Path, help="Optional original 15m dataset for independent aggregation comparison")
    args = parser.parse_args()
    months = [str(p) for p in pd.period_range(args.start, args.end, freq="M")]
    raw = args.out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    completed, failed = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_month, month, raw): month for month in months}
        for future in concurrent.futures.as_completed(futures):
            month = futures[future]
            try:
                record = future.result()
                completed.append(record)
                print(f"{month} CHECKSUM_OK {record['bytes']} bytes", flush=True)
            except Exception as exc:
                failed.append({"month": month, "error": f"{type(exc).__name__}: {exc}"})
                print(f"{month} FAILED {type(exc).__name__}: {exc}", flush=True)
    completed.sort(key=lambda x: x["month"])
    manifest = {"source": BASE, "requested_months": months, "archives": completed, "failures": sorted(failed, key=lambda x: x["month"])}
    (args.out / "download_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if failed:
        raise SystemExit(f"Download incomplete: {len(failed)} failures. No normalized dataset written.")
    data = pd.concat([read_month(raw / item["file"]) for item in completed], ignore_index=True)
    report = audit(data, args.start, args.end)
    (args.out / "data_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    fatal = ["duplicate_open_times", "off_grid_bars", "bad_close_times", "outside_requested_range", "invalid_ohlc_rows", "negative_volume_rows", "invalid_taker_rows", "nonfinite_numeric_rows"]
    if not report["sorted_ascending"] or any(report[k] for k in fatal):
        raise SystemExit("Data audit failed. See data_audit.json. No normalized dataset written.")
    target = args.out / f"BTCUSDT_4h_{args.start}_{args.end}.csv.gz"
    data.to_csv(target, index=False, compression={"method": "gzip", "mtime": 0})
    report["normalized_file"] = str(target.resolve())
    report["normalized_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    (args.out / "data_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.compare_15m:
        comparison = compare_15m(data, args.compare_15m)
        (args.out / "comparison_15m_to_4h.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
        pd.DataFrame(comparison['field_discrepancies']).to_csv(args.out / 'aggregation_field_discrepancies.csv', index=False)
        pd.DataFrame(comparison['mismatched_windows']).to_csv(args.out / 'aggregation_window_discrepancies.csv', index=False)
        if comparison['status'] != 'PASS':
            print(json.dumps({'cross_timeframe_exact_equality': 'FAIL', 'official_4h_input': 'VALID',
                              'mismatched_windows': comparison['mismatched_windows_count'],
                              'target_color_mismatches': comparison['all_8766_target_color_mismatches'],
                              'action': 'Keep official4h unchanged; cross-timeframe comparison is diagnostic only'}), flush=True)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
