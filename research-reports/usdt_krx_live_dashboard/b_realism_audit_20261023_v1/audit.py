"""Read-only saved-trade audit; no strategy execution, API credentials or orders.
Run: python -B audit.py
Outputs: borrow_sensitivity.csv, reverse_fee_005.csv, validation.json.
Uniform daily-rate scenarios are NOT a historical borrowing-cost reconstruction.
"""
from __future__ import annotations
import csv
import json
from datetime import datetime
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 28
D = Decimal
ROOT = Path(__file__).resolve().parent
Q = D("170000")
BASE_NET = D("41295918.91188297")
BASE_SCORE = D("16.7054302006977")
EXPECTED_SHORT_NET = D("19107091.235301048")

def write_csv(name, rows):
    if not rows:
        raise ValueError("No rows to write")
    with (ROOT / name).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def costs(spot, future):
    """Existing published PAPER fee assumptions, not a broker quote."""
    return (spot*Q*D(".0005") + D(17)*D(600)
            + future*Q*D(".000003157")
            + spot*Q*D(".0002") + future*Q*D(".0002"))

def main():
    with (ROOT/"reverse_cycles_source_extract.csv").open(encoding="utf-8", newline="") as f:
        data = list(csv.DictReader(f))
    if len(data) != 18 or len({r["cycle_id"] for r in data}) != 18:
        raise ValueError("Expected exactly 18 distinct inverse-direction cycles")
    for r in data:
        a = datetime.fromisoformat(r["entry"])
        b = datetime.fromisoformat(r["exit"])
        if int((b-a).total_seconds()/60) != int(r["hold_minutes"]):
            raise ValueError("Holding time mismatch: "+r["cycle_id"])
        # Scenario: borrow at entry, repay at exit; KST calendar-day billing.
        # Same-day repayment has one charged day. No pre-borrowing or settlement delay.
        r["billing_days"] = max(1, (b.date()-a.date()).days)
    short_net = sum(D(r["net"]) for r in data)
    if abs(short_net-EXPECTED_SHORT_NET) > D(".01"):
        raise ValueError("Saved inverse-cycle net total does not reconcile")
    scenarios, detail = [], []
    for rate in map(D, ("0", ".0001", ".0003", ".0005")):
        fees = [Q*rate*D(r["billing_days"])*D(r["exit_spot"]) for r in data]
        fee_total = sum(fees)
        return_deduction = sum(f/(Q*D(r["entry_spot"]))*100 for f,r in zip(fees,data))
        loss_ids = [int(r["cycle_id"]) for r,f in zip(data,fees) if D(r["net"])-f < 0]
        scenarios.append({
            "mode": "UNIFORM_RATE_FIXED_SAVED_TRADES_NOT_RERUN",
            "daily_borrow_rate_pct": str(rate*100),
            "borrow_fee_krw": str(fee_total),
            "all42_net_after_scenario_krw": str(BASE_NET-fee_total),
            "cycle_return_sum_after_scenario_pct": str(BASE_SCORE-return_deduction),
            "reverse18_net_after_scenario_krw": str(short_net-fee_total),
            "saved_wins_after_cost": 42-len(loss_ids),
            "saved_losses_after_cost": len(loss_ids),
            "losing_cycle_ids": ";".join(map(str,loss_ids)),
            "availability_margin_path_revalidated": False
        })
        if rate == D(".0005"):
            for r,f in zip(data,fees):
                detail.append({
                    "cycle_id": r["cycle_id"], "billing_days_assumed": r["billing_days"],
                    "exit_price_proxy_krw": r["exit_spot"], "saved_net_krw": r["net"],
                    "scenario_borrow_fee_krw": str(f),
                    "scenario_net_krw": str(D(r["net"])-f),
                    "historical_rate_verified": False
                })
    # 2025-01-07 entry to 2025-01-20 11:30 mark, not a realized exit.
    spot_gross = (D("1469")-D("1524"))*Q
    future_gross = (D("1452.1")-D("1458.3"))*Q
    entry_cost = costs(D("1469"),D("1458.3"))
    hypothetical_exit_cost = costs(D("1524"),D("1452.1"))
    jan_net = spot_gross+future_gross-entry_cost-hypothetical_exit_cost
    expected_jan_net = D("-10881082.582576007")
    if abs(jan_net-expected_jan_net) > D(".01"):
        raise ValueError("January loss decomposition does not reconcile")
    # A recognized-collateral example only; price 1450 is an assumption, not live.
    collateral = Q*D("1450")/D(".85")
    validation = {
        "arithmetic_status": "PASS",
        "reverse_cycle_count": len(data),
        "total_billing_days_assumed": sum(r["billing_days"] for r in data),
        "reverse_net_reconciliation_difference_krw": str(short_net-EXPECTED_SHORT_NET),
        "january_loss": {
            "spot_gross_krw": str(spot_gross),
            "futures_gross_krw": str(future_gross),
            "paid_entry_cost_krw": str(entry_cost),
            "estimated_exit_cost_krw": str(hypothetical_exit_cost),
            "hypothetical_liquidation_net_krw": str(jan_net),
            "difference_from_saved_krw": str(jan_net-expected_jan_net),
            "not_a_realized_exit": True,
            "contract_and_quote_identity_confirmed": False
        },
        "collateral_example_at_1450_krw_and_85pct_ltv": str(collateral),
        "full_backtest_rerun": False, "new_orders": False,
        "originals_modified": False, "oos_accessed": False,
        "not_validated": [
            "actual USDT lending availability, user eligibility and capacity",
            "historical date-specific lending rates and borrowing/repayment timestamps",
            "lending collateral liquidation and full margin path",
            "January 2025 exact historical margin rates and account settlement",
            "verified intraday roll prices and original quote contract identity",
            "future period forward validation"
        ]
    }
    write_csv("borrow_sensitivity.csv",scenarios)
    write_csv("reverse_fee_005.csv",detail)
    (ROOT/"validation.json").write_text(json.dumps(validation,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"scenarios":scenarios,"validation":validation},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
