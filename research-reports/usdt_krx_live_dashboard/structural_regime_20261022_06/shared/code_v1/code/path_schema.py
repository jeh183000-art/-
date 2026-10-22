# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Frozen path-derivative rule schema; use code/bootstrap.py.
from typing import TypedDict, Literal
import numpy as np

class PathRule(TypedDict, total=False):
    family: str
    long_entry_gap_pct: float
    short_entry_gap_pct: float
    long_recovery_pp: float
    short_recovery_pp: float
    long_absolute_exit_gap_pct: float | None
    short_absolute_exit_gap_pct: float | None
    confirmation_pp: float
    confirmation_expiry_calendar_minutes: int | None
    max_hold_minutes: float | None
    gap_stop_pp: float | None
    pnl_stop_pct: float | None
    pnl_profit_pct: float
    stall_minutes: float
    slippage_bp: float
    allowed_direction: int
    entry_session: str
    minimum_minute_volume: float
    pnl_profit_long_pct: float
    pnl_profit_short_pct: float
    cooldown_minutes: float
    confirmation_min_observations: int
    gap_exit_enabled: bool
    threshold_mode: Literal['fixed','mean_shift','median_shift','volatility']
    window_observations: int
    center_weight: float
    volatility_entry_scale: bool
    volatility_recovery_scale: bool

class Context(TypedDict):
    night: np.ndarray
    volume: np.ndarray
