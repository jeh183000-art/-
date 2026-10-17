# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "numba"]
# ///
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Final

import numpy as np

VECTOR_NAMES: Final = ("times", "month_ids", "month_end", "contract_ids", "gap", "spot_open", "spot_close", "future_open", "future_close", "roll_flag", "roll_old_open", "old_contract_ids", "continuous_prev", "settlement_due", "settlement_price", "settlement_spot_mark", "initial_rate", "maintenance_rate")
KernelResult = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]
Kernel = Callable[..., KernelResult]


@dataclass(frozen=True, slots=True)
class Market:
    vectors: tuple[np.ndarray, ...]
    timestamps: tuple[str, ...]
    codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Condition:
    candidate_id: str
    direction: int
    exit_mode: int
    entry: float
    spacing: float
    recovery: float
    slippage: float = 2.0
    clearing: bool = True
    one_fill_per_bar: bool = False
    capital_limited: bool = False


@dataclass(frozen=True, slots=True)
class Execution:
    summary: np.ndarray
    trades: np.ndarray
    events: np.ndarray
    residuals: np.ndarray
    monthly: np.ndarray
    stage_capacity: int
    retries: int
    event_capacity: int
    trade_capacity: int


def run(kernel: Kernel, market: Market, case: Condition) -> Execution:
    vectors = market.vectors
    adverse = -float(vectors[4].min()) if case.direction == 1 else float(vectors[4].max())
    capacity = max(2, math.ceil(max(0.0, adverse - case.entry) / case.spacing) + 3)
    event_capacity, trade_capacity, retries = 16384, 4096, 0
    while True:
        result = kernel(*vectors[:4], case.direction, case.exit_mode, case.entry, case.recovery,
                        *vectors[4:], case.slippage, case.clearing, case.direction == -1,
                        case.capital_limited, case.spacing, case.one_fill_per_bar,
                        capacity, event_capacity, trade_capacity)
        summary, trades, events, residuals, monthly = result
        if summary[41] == 0 and summary[42] == 0:
            break
        event_capacity *= 2 if summary[41] else 1
        trade_capacity *= 2 if summary[42] else 1
        retries += 1
    ledger_net = float(trades[:, 22].sum() + residuals[:, 17].sum())
    assert abs(float(summary[13]) - ledger_net) < 0.01, (case.candidate_id, summary[13], ledger_net)
    assert len(trades) == int(summary[1])
    assert len(residuals) == int(summary[23])
    assert int(summary[0]) == len(trades) + len(residuals)
    if not case.capital_limited:
        assert all(summary[index] == 0 for index in (25, 26, 27)), "Unlimited funding gates unexpectedly rejected admission"
    if len(trades):
        assert np.all(trades[:, 4] > trades[:, 3]) and np.all(trades[:, 13] > trades[:, 12])
        assert np.all(vectors[12][trades[:, 4].astype(int)])
        assert np.all(vectors[12][trades[:, 13].astype(int)])
    assert len({(int(row[0])) for row in residuals}) == len(residuals)
    return Execution(summary, trades, events, residuals, monthly, capacity, retries, event_capacity, trade_capacity)
