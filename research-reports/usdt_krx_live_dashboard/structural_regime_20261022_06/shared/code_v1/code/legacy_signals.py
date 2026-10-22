# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Prior observations only; use code/bootstrap.py.
from __future__ import annotations
import importlib.util
import hashlib
from typing import assert_never
from pathlib import Path
import numpy as np
from path_schema import PathRule, Context

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT.parents[1] / 'studies/single_set_hypotheses_20261020_01/code/signals.py'

def statistics(v: tuple[np.ndarray, ...], window: int) -> np.ndarray:
    """Exclude current bar; reset at a contract roll or >30-calendar-minute gap."""
    resets = v[9].astype(bool).copy()
    resets[1:] |= np.diff(v[0]) > 30
    identity = hashlib.sha256(v[0].tobytes()+v[4].tobytes()+resets.tobytes()).hexdigest()[:16]
    path = ROOT / 'feature_cache' / f'path_v1_{window}_{identity}.npz'
    if path.exists():
        with np.load(path) as saved:
            return saved['stats']
    spec = importlib.util.spec_from_file_location('frozen_prior_trailing', PRIOR)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    resets = v[9].astype(bool).copy()
    resets[1:] |= np.diff(v[0]) > 30
    values = module.trailing(v[4], resets, window)
    path.parent.mkdir(exist_ok=True)
    np.savez_compressed(path, stats=values)
    return values

def prepare(rule: PathRule, v: tuple[np.ndarray, ...], context: Context) -> tuple:
    """Snapshot entry thresholds and recovery at the actual signal, never a future bar."""
    gap = v[4]
    n = len(gap)
    low = np.full(n, float(rule['long_entry_gap_pct']))
    high = np.full(n, float(rule['short_entry_gap_pct']))
    rl = np.full(n, float(rule.get('long_recovery_pp') or 0.))
    rs = np.full(n, float(rule.get('short_recovery_pp') or 0.))
    mode = rule.get('threshold_mode', 'fixed')
    if mode != 'fixed':
        stat = statistics(v, int(rule['window_observations']))
        match mode:
            case 'mean_shift':
                center = stat[:, 0] * float(rule['center_weight'])
            case 'median_shift':
                center = stat[:, 1] * float(rule['center_weight'])
            case 'volatility':
                center = stat[:, 0] * float(rule.get('center_weight') or 0.)
            case unknown:
                assert_never(unknown)
        scale = np.clip(stat[:, 2] / .25, .5, 2.5)
        if rule.get('volatility_entry_scale'):
            low *= scale
            high *= scale
        low = np.minimum(-.05, low + center)
        high = np.maximum(.05, high + center)
        if rule.get('volatility_recovery_scale'):
            rl *= np.clip(stat[:, 2] / .25, .5, 2.)
            rs *= np.clip(stat[:, 2] / .25, .5, 2.)
    long = np.zeros(n, dtype=np.bool_)
    short = long.copy()
    long[1:] = (gap[1:] <= low[1:]) & (gap[:-1] > low[:-1])
    short[1:] = (gap[1:] >= high[1:]) & (gap[:-1] < high[:-1])
    valid = v[12] & ~v[9].astype(bool)
    session = rule.get('entry_session')
    if session == 'regular':
        valid &= ~context['night']
    if session == 'night':
        valid &= context['night']
    if rule.get('minimum_minute_volume') is not None:
        valid &= context['volume'] >= float(rule['minimum_minute_volume'])
    sign = np.zeros(n, dtype=np.int64)
    direction = int(rule.get('allowed_direction') or 0)
    if direction in (0, 1):
        sign[long & valid] = 1
    if direction in (0, -1):
        sign[short & valid & (sign == 0)] = -1
    options = np.array((float(rule.get('pnl_profit_long_pct', -1)),
                        float(rule.get('pnl_profit_short_pct', -1)),
                        float(rule.get('cooldown_minutes') or 0),
                        float(rule.get('confirmation_expiry_calendar_minutes') or 240),
                        float(rule.get('confirmation_min_observations') or 0),
                        float(rule.get('gap_exit_enabled', True))), dtype=np.float64)
    return (sign, np.zeros(n, dtype=np.bool_), np.zeros(n, dtype=np.bool_), gap + rl, gap - rs, 1,
            float(rule.get('confirmation_pp') or 0), float(rule.get('max_hold_minutes') or 0),
            float(rule.get('gap_stop_pp') or 0), float(rule.get('pnl_profit_pct') or 0),
            float(rule.get('pnl_stop_pct') or 0), float(rule.get('stall_minutes') or 0),
            options, float(rule.get('slippage_bp') or 2))
