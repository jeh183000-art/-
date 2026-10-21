"""Build an immutable preregistration; this does NOT run a backtest."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

STUDY = "lump17_sweep_20261021_01"
BASE_COMMIT = "9bf0419af434faa8a7ed80adac46bd86cf2e3f60"
BASE_ROOT = "research-reports/usdt_krx_live_dashboard/split_vs_lump17_20261021_01/batches/batch_0001"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def build() -> dict:
    rows = []

    def add(group: str, family: str, el: float, es: float, rl=None, rs=None,
            tl=None, ts=None, confirm=0.0) -> None:
        rule = {
            "family": family,
            "long_entry_gap_pct": -float(el),
            "short_entry_gap_pct": float(es),
            "long_recovery_pp": None if rl is None else float(rl),
            "short_recovery_pp": None if rs is None else float(rs),
            "long_absolute_exit_gap_pct": None if tl is None else float(tl),
            "short_absolute_exit_gap_pct": None if ts is None else float(ts),
            "confirmation_pp": float(confirm),
            "confirmation_expiry_calendar_minutes": 240 if confirm else None,
            "max_hold_minutes": None,
            "gap_stop_pp": None,
            "pnl_stop_pct": None,
        }
        rows.append({"candidate_id": f"L17-01-{len(rows)+1:03d}", "group": group,
                     "rule": rule, "rule_sha256": hashlib.sha256(canonical(rule)).hexdigest()})

    # 5 x 5 minus the existing champion: 24 NEW symmetric conditions.
    for e in (0.7, 0.9, 1.0, 1.1, 1.3):
        for r in (0.3, 0.4, 0.5, 0.6, 0.8):
            if (e, r) != (1.0, 0.5):
                add("symmetric_relative", "relative", e, e, r, r)

    # (long entry magnitude, long recovery, short entry magnitude, short recovery)
    asym = (
        (0.8, 0.5, 1.2, 0.5), (1.2, 0.5, 0.8, 0.5),
        (1.0, 0.4, 1.0, 0.6), (1.0, 0.6, 1.0, 0.4),
        (0.8, 0.4, 1.2, 0.6), (1.2, 0.6, 0.8, 0.4),
        (1.0, 0.5, 1.5, 0.8), (1.5, 0.8, 1.0, 0.5),
        (0.8, 0.6, 1.5, 0.5), (1.5, 0.5, 0.8, 0.6),
        (1.2, 0.4, 1.0, 0.8), (1.0, 0.8, 1.2, 0.4),
    )
    for el, rl, es, rs in asym:
        add("asymmetric_relative", "relative", el, es, rl, rs)

    # Signed absolute exits; includes partial recovery, zero, and sign reversal.
    absolute = (
        (0.6, -0.2, 0.2), (0.9, -0.3, 0.3), (1.2, -0.6, 0.6),
        (0.8, 0.0, 0.0), (1.2, 0.0, 0.0), (0.8, 0.4, -0.4),
        (1.5, 1.5, -1.5), (2.0, 1.0, -1.0),
    )
    for e, tl, ts in absolute:
        add("fixed_absolute", "absolute", e, e, tl=tl, ts=ts)

    for e, c, r in ((0.8, 0.05, 0.4), (1.0, 0.1, 0.5),
                    (1.0, 0.2, 0.6), (1.3, 0.1, 0.5),
                    (1.5, 0.1, 0.7), (2.0, 0.2, 1.0)):
        add("reversal_confirmation", "reversal", e, e, r, r, confirm=c)

    expected = {"symmetric_relative": 24, "asymmetric_relative": 12,
                "fixed_absolute": 8, "reversal_confirmation": 6}
    if len(rows) != 50 or dict(Counter(r["group"] for r in rows)) != expected:
        raise ValueError("The registered grid must contain exactly 50 conditions.")
    if len({r["rule_sha256"] for r in rows}) != 50:
        raise ValueError("Duplicate rule in the new grid.")
    for row in rows:
        r = row["rule"]
        if not r["long_entry_gap_pct"] < 0 < r["short_entry_gap_pct"]:
            raise ValueError("Invalid signed entry thresholds.")
        if r["family"] == "absolute":
            if not (r["long_absolute_exit_gap_pct"] > r["long_entry_gap_pct"] and
                    r["short_absolute_exit_gap_pct"] < r["short_entry_gap_pct"]):
                raise ValueError("Exit is not in the favourable direction.")
        elif r["long_recovery_pp"] <= 0 or r["short_recovery_pp"] <= 0:
            raise ValueError("Recovery must be positive.")

    return {
        "study_id": STUDY, "batch": "batch_0001", "status": "PREREGISTERED_NOT_EXECUTED",
        "new_conditions": 50, "groups": expected,
        "reference_commit": BASE_COMMIT, "reference_root": BASE_ROOT,
        "reference_candidate": "S1-050-LUMP17",
        "reference_score_pct": 13.15221660791525,
        "reference_net_krw_approx": 32356627.767363,
        "reference_cycles": 45,
        "champion_regression_counts_as_new_condition": False,
        "controls": {
            "atomic_initial_contracts": 17, "atomic_initial_usdt": 170000,
            "maximum_simultaneous_contracts": 17, "global_position_slots": 1,
            "additional_entries": False, "partial_fill_or_downsize": False,
            "future_initial_cash_krw": 30000000,
            "external_future_deposits": False, "inter_account_transfers": False,
            "spot_cash_limit": None, "spot_funding": "ASSUMED_SUFFICIENT_NOT_USER_BALANCE",
            "paper_only": True, "final_oos_access": False,
        },
        "input_scope": "Existing approved EXPLORATORY 2026-01-01..10-15 KRX business dates and verified required night boundaries; no new data or protected Final OOS",
        "source_sha256": {
            "matched_simulation_bars.csv": "62becd7d50e05bdcf47010cdcdfdd8178bbe2ef1d8099a84ab18fae8fea19fbd",
            "margin_schedule.csv": "910816bc61c9d9b7361bec370e225bfeae9cde0f11b889265cb4409ecb9344b8",
        },
        "costs": {
            "spot_fee_per_side": 0.0005, "futures_fee_per_contract_per_side_krw": 600,
            "clearing_rate": 0.000003157, "slippage_bp_per_side_per_leg": 2,
            "borrow_cost": "UNVERIFIED_NOT_INCLUDED", "perpetual_funding": "NOT_APPLICABLE",
        },
        "score": "Unrounded arithmetic sum of completed-cycle net / absolute spot entry notional * 100; not account ROI",
        "baseline_fee_and_execution_policy": "Inherit fixed reference; version and hash every code change before running",
        "grid_sha256": hashlib.sha256(canonical(rows)).hexdigest(),
        "conditions": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    spec = build()
    if args.output is not None:
        # Exclusive create: never replace preregistrations or prior results.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(spec, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": spec["status"], "new_conditions": 50,
                      "groups": spec["groups"], "grid_sha256": spec["grid_sha256"],
                      "backtest_executed": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
