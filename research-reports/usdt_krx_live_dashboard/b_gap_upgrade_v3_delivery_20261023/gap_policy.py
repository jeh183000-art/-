"""Conservative quote-log gap policy for B strategy sensitivity PAPER.

Uses only available observations; small missing intervals never get synthetic
quotes, signals, marks or fills. No real futures contract is authenticated.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import time

@dataclass(frozen=True)
class Boundary:
    kind: str
    allowed: bool
    missing_minutes: int = 0
    reason: str = ""


def classify_boundary(prev, curr, official: dict, ranks: dict[str, int], tolerance: int) -> Boundary:
    """Classify observed-quote adjacency. tolerance = 0/1/2 minutes only.

    Quote-like inputs need `.t` (datetime) and `.reference_contract` (string).
    The reference month is *not* certified actual log contract identity.
    """
    assert tolerance in (0, 1, 2)
    seconds = (curr.t - prev.t).total_seconds()
    if seconds <= 0 or seconds % 60 != 0:
        return Boundary('INVALID_CLOCK', False, reason='not positive whole-minute interval')
    elapsed = int(seconds // 60)
    same_contract = prev.reference_contract == curr.reference_contract
    if prev.t.date() == curr.t.date():
        if not same_contract:
            return Boundary('REF_CHANGE', False, reason='reference contract changed intraday')
        if elapsed == 1:
            return Boundary('CONTIGUOUS', True)
        missed = elapsed - 1
        if missed <= tolerance:
            return Boundary('INTRADAY_SMALL_GAP', True, missed, 'unobserved minutes; no replay fill')
        return Boundary('INTRADAY_LARGE_GAP', False, missed, 'gap exceeds fixed sensitivity tolerance')
    a = prev.t.strftime('%Y%m%d')
    b = curr.t.strftime('%Y%m%d')
    if a not in official or b not in official or a not in ranks or b not in ranks:
        return Boundary('OFFICIAL_CALENDAR_NOT_VERIFIED', False)
    if ranks[b] != ranks[a] + 1:
        return Boundary('MISSING_OFFICIAL_TRADING_DATES', False)
    if not same_contract or official[a]['contract_code_kis'] != official[b]['contract_code_kis']:
        return Boundary('REF_CHANGE_UNVERIFIED_ROLL', False)
    if float(official[a]['official_volume']) <= 0 or float(official[b]['official_volume']) <= 0:
        return Boundary('UNVERIFIED_VOLUME', False)
    if official[a]['expiry_date'] < prev.t.date().isoformat() or official[b]['expiry_date'] < curr.t.date().isoformat():
        return Boundary('EXPIRED_REFERENCE_CONTRACT', False)
    expected_prev_end = time(11, 30) if official[a]['expiry_date'] == prev.t.date().isoformat() else time(15, 30)
    close_min = expected_prev_end.hour * 60 + expected_prev_end.minute
    pmin = prev.t.hour * 60 + prev.t.minute
    nmin = curr.t.hour * 60 + curr.t.minute
    missed_end = close_min - pmin
    missed_start = nmin - 9 * 60
    if missed_end < 0 or missed_start < 0:
        return Boundary('INVALID_LOGGER_CLOCK', False)
    if missed_end == 0 and missed_start == 0:
        return Boundary('NORMAL_CLOSED_SESSION', True, 0, 'no fills outside logger window')
    if missed_end <= tolerance and missed_start <= tolerance:
        return Boundary('SESSION_EDGE_SMALL_GAP', True, missed_end + missed_start,
                        'some logger-window edge quotes unavailable')
    return Boundary('LOGGER_WINDOW_EDGE_MISSING', False, missed_end + missed_start)
