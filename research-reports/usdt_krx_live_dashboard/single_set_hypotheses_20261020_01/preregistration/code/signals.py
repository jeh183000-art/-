# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Imported by study.py; trailing distributions exclude the signal bar.
from __future__ import annotations

from bisect import bisect_left, insort
from collections import deque
from dataclasses import dataclass, asdict
from math import sqrt

import numpy as np


@dataclass(frozen=True, slots=True)
class Rule:
    candidate_id: str
    family: str
    direction: int
    entry: float = 0.8
    target: float = 0.0
    recovery: float = 0.5
    window: int = 0
    fraction: float = 1.0
    confirm: float = 0.0
    max_hold: float = 0.0
    gap_stop: float = 0.0
    pnl_profit: float = 0.0
    pnl_stop: float = 0.0
    stall: float = 0.0


def grid() -> list[Rule]:
    rows = []
    specs = []
    for e, t in ((0.3, -0.1), (0.3, 0.3), (1.0, 0.0), (2.5, 0.0), (4.0, 0.0)):
        specs.append(dict(family="absolute", entry=e, target=t))
    for e, r in ((0.3, 0.2), (0.3, 0.5), (0.8, 0.5), (2.5, 1.5)):
        specs.append(dict(family="relative", entry=e, recovery=r))
    for f, w, frac in (("mean", 60, 0.5), ("mean", 60, 1.0), ("median", 60, 1.0), ("median", 240, 1.0)):
        specs.append(dict(family=f, entry=0.3, window=w, fraction=frac))
    for f, w, e in (("quantile", 60, 0.1), ("quantile", 240, 0.1), ("zscore", 60, 1.5), ("zscore", 240, 1.5)):
        specs.append(dict(family=f, entry=e, window=w))
    for e, c, r in ((0.5, 0.05, 0.3), (1.0, 0.1, 0.5), (2.0, 0.2, 1.0)):
        specs.append(dict(family="reversal", entry=e, confirm=c, recovery=r))
    for kw in (dict(max_hold=240.0), dict(gap_stop=0.5), dict(pnl_profit=0.2, pnl_stop=0.5), dict(stall=120.0)):
        specs.append(dict(family="risk_exit", entry=0.8, recovery=0.5, **kw))
    for spec in specs:
        for direction in (1, -1):
            rows.append(Rule(candidate_id=f"S1-{len(rows)+1:03d}", direction=direction, **spec))
    rows.append(Rule("S1-049", "absolute", 0, entry=0.5, target=0.0))
    rows.append(Rule("S1-050", "relative", 0, entry=1.0, recovery=0.5))
    assert len(rows) == 50
    return rows


def trailing(gap: np.ndarray, rolls: np.ndarray, window: int) -> np.ndarray:
    out = np.full((len(gap), 6), np.nan)
    ordered = []
    history = deque()
    total = squares = 0.0
    for i, x in enumerate(gap):
        if rolls[i]:
            ordered.clear()
            history.clear()
            total = squares = 0.0
        if len(history) == window:
            def q(p: float) -> float:
                a = p * (window - 1)
                lo = int(a)
                hi = min(lo + 1, window - 1)
                return ordered[lo] * (1 - a + lo) + ordered[hi] * (a - lo)
            mean = total / window
            out[i] = (mean, q(0.5), sqrt(max(0.0, squares / window - mean * mean)), q(0.1), q(0.9), q(0.5))
        history.append(x)
        insort(ordered, x)
        total += x
        squares += x * x
        if len(history) > window:
            old = history.popleft()
            ordered.pop(bisect_left(ordered, old))
            total -= old
            squares -= old * old
    return out


def prepare(rule: Rule, v: tuple[np.ndarray, ...], stats: dict[int, np.ndarray]):
    gap = v[4]
    center = np.zeros(len(gap))
    entry = np.zeros(len(gap), dtype=np.int64)
    exits = [np.zeros(len(gap), dtype=np.bool_), np.zeros(len(gap), dtype=np.bool_)]
    mode = 1
    family = rule.family
    for d in (1, -1):
        if rule.direction not in (0, d):
            continue
        score = d * gap
        threshold = np.full(len(gap), -rule.entry)
        exit_values = score >= rule.target
        if family in ("mean", "median"):
            center = stats[rule.window][:, 0 if family == "mean" else 1]
            score = d * (gap - center)
            mode = 2
        elif family == "quantile":
            threshold = stats[rule.window][:, 3 if d == 1 else 4]
            score = gap
            exited = gap >= stats[rule.window][:, 5] if d == 1 else gap <= stats[rule.window][:, 5]
            exit_values = exited
            mode = 3
        elif family == "zscore":
            center = stats[rule.window][:, 0]
            std = stats[rule.window][:, 2]
            score = np.divide(d * (gap - center), std, out=np.full(len(gap), np.nan), where=std > 1e-8)
            exit_values = score >= 0
            mode = 3
        elif family == "absolute":
            mode = 0
            center = np.full(len(gap), rule.target)
        crossed = np.zeros(len(gap), dtype=np.bool_)
        if family == "quantile" and d == -1:
            crossed[1:] = (score[1:] >= threshold[1:]) & (score[:-1] < threshold[:-1])
        else:
            crossed[1:] = (score[1:] <= threshold[1:]) & (score[:-1] > threshold[:-1])
        crossed &= v[12] & ~v[9].astype(bool)
        entry[crossed & (entry == 0)] = d
        exits[0 if d == 1 else 1] = exit_values
    return entry, exits[0], exits[1], center, mode
