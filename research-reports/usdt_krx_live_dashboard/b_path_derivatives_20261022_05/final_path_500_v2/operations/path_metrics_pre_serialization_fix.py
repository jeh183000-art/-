# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Saved-ledger attribution, not a new simulation; use code/bootstrap.py.
from __future__ import annotations
import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict
import numpy as np
from path_schema import PathRule

class ExitRow(TypedDict):
    cycle_id: int
    signal_row: int
    signal_gap_pct: float
    observed_liquidation_return_pct: float
    gap_target_pct: float
    profit_target_pct: float
    gap: bool
    profit: bool
    loss_stop: bool
    time_stop: bool
    stall_stop: bool
    reason_bits: int

class Metrics(TypedDict):
    exit_gap_only: int
    exit_profit_only: int
    exit_gap_profit_both: int
    exit_gap_any: int
    exit_profit_any: int
    exit_other: int
    exit_loss_stop: int
    exit_time: int
    exit_stall: int
    execution_path_sha256: str
    completed_loss_cycles: int
    top3_positive_return_share_pct: float | None
    top5_positive_return_share_pct: float | None

@dataclass(frozen=True, slots=True)
class MetricContext:
    rule: PathRule
    v: tuple[np.ndarray, ...]
    trades: np.ndarray
    ledger: np.ndarray
    events: np.ndarray
    out: Path

def enrich(context: MetricContext) -> Metrics:
    """Independently derive profit/stop attribution from close-phase paid-cost marks."""
    rule, v, trades, ledger, out = context.rule, context.v, context.trades, context.ledger, context.out
    rows: list[ExitRow] = []
    returns = []
    for trade in trades:
        i = int(trade[2])
        sign = int(trade[4])
        limit = float(rule.get('pnl_profit_long_pct' if sign == 1 else 'pnl_profit_short_pct',
                               rule.get('pnl_profit_pct') or 0))
        spot, future = v[6][i], v[8][i]
        close_cost = spot*170000*.0005 + 10200 + future*170000*.000003157 + (spot+future)*170000*.0002
        ret = (ledger[i,1,6] - close_cost) / (trade[5]*170000) * 100
        bits = int(trade[18])
        profit = bool(bits & 4) and limit > 0 and ret >= limit - 1e-10
        loss_limit = float(rule.get('pnl_stop_pct') or 0)
        loss = bool(bits & 4) and loss_limit > 0 and ret <= -loss_limit + 1e-10
        assert not (bits & 4) or profit or loss
        rows.append(ExitRow(cycle_id=int(trade[17]),signal_row=i,signal_gap_pct=float(v[4][i]),
            observed_liquidation_return_pct=float(ret),gap_target_pct=float(trade[16]),
            profit_target_pct=limit,gap=bool(bits&1),profit=profit,loss_stop=loss or bool(bits&2),
            time_stop=bool(bits&8),stall_stop=bool(bits&16),reason_bits=bits))
        returns.append(float(trade[13]/(trade[5]*170000)*100))
    with (out/'exit_attribution.csv').open('x',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(ExitRow.__annotations__))
        writer.writeheader()
        writer.writerows(rows)
    positive=sorted((x for x in returns if x>0),reverse=True)
    total=sum(positive)
    fingerprint=hashlib.sha256(ledger)
    fingerprint.update(np.ascontiguousarray(context.events[:,:13]))
    return Metrics(execution_path_sha256=fingerprint.hexdigest(),exit_gap_only=sum(r['gap'] and not r['profit'] for r in rows),
        exit_profit_only=sum(r['profit'] and not r['gap'] for r in rows),
        exit_gap_profit_both=sum(r['gap'] and r['profit'] for r in rows),
        exit_gap_any=sum(r['gap'] for r in rows),exit_profit_any=sum(r['profit'] for r in rows),
        exit_other=sum(not r['gap'] and not r['profit'] for r in rows),
        exit_loss_stop=sum(r['loss_stop'] for r in rows),exit_time=sum(r['time_stop'] for r in rows),
        exit_stall=sum(r['stall_stop'] for r in rows),completed_loss_cycles=sum(x<0 for x in returns),
        top3_positive_return_share_pct=sum(positive[:3])/total*100 if total else None,
        top5_positive_return_share_pct=sum(positive[:5])/total*100 if total else None)
