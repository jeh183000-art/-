# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy"]
# ///
from __future__ import annotations

import csv
import gzip
import importlib.metadata
import json
import platform
import shutil
from dataclasses import asdict
from pathlib import Path

from package_revalidation_batch import finalize
from research_storage import STORAGE, require_d_path


def write_table(path: Path, rows, fields=None) -> None:
    path = require_d_path(path)
    names = fields or list(rows[0])
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def save_raw(stream, names, values, case, market) -> None:
    writer = csv.writer(stream)
    for value in values:
        writer.writerow([case.candidate_id, *value.tolist()])


def finalize_batch(batch: Path, rows, cycles, conditions) -> Path:
    batch = require_d_path(batch)
    write_table(batch / "results.csv", rows)
    write_table(batch / "risks.csv", [{key: row[key] for key in ("candidate_id", "max_open_evaluation_loss_krw", "mdd_krw", "completed_cycle_mdd_pp", "max_simultaneous_contracts", "max_initial_margin_krw", "max_maintenance_margin_krw", "required_spot_cash_krw", "required_futures_cash_krw", "max_futures_adverse_krw", "max_adverse_gap_pp", "residual_sets", "residual_unrealized_gross_krw", "residual_net_after_close_cost_krw")} for row in rows])
    write_table(batch / "costs.csv", [{key: row[key] for key in ("candidate_id", "fee_policy", "slippage", "fees_krw", "slippage_krw", "funding_krw")} for row in rows])
    cycle_fields = ["candidate_id", "cycle_id", "complete", "entry_notional_krw", "cycle_net_pnl_krw", "closed_net_pnl_krw", "residual_net_after_close_cost_krw", "cycle_return_pct", "closed_sets", "open_sets", "first_entry_kst", "exit_or_evaluation_kst", "hold_minutes"]
    write_table(batch / "cycles.csv", cycles, cycle_fields)
    (batch / "settings.json").write_text(json.dumps({"conditions": [asdict(case) for case in conditions], "funding_mode": "UNLIMITED_EXTERNAL_FUNDING_RESEARCH_ONLY", "cycle_denominator": "Sum of absolute spot entry notionals of every set in that cycle; no exit notional or futures margin in denominator", "return_aggregation": "Unrounded arithmetic sum of completed cycle net returns; residual cycles excluded and separately marked", "funding_cost": "KRX dated futures: perpetual funding not applicable", "reverse_borrow": "Unverified availability and borrow cost; reverse is theoretical only", "same_stage_reentry": "Allowed only after that stage closes and a new crossing occurs", "memory_capacity": "Data extremes determine storage allocation only, never entry/exit choices", "initial_cash": 0, "initial_futures_cash": 0, "one_fill_sensitivity": "When true: fill the shallowest newly crossed unheld stage only; discard unfilled crossings without deferral"}, indent=2) + "\n", encoding="utf-8")
    (batch / "environment.json").write_text(json.dumps({"python": platform.python_version(), "numpy": importlib.metadata.version("numpy"), "numba": importlib.metadata.version("numba"), "original_research_runtime_modified": False}, indent=2) + "\n", encoding="utf-8")
    best = max((row for row in rows if row["completed_cycles"]), key=lambda row: row["cumulative_simple_return_pct"], default=None)
    report = "# 무제한 자금 탐색 배치\n\n연구 범위: 승인된 2026-01-01~10-15 KRX 거래일, 정규장·야간장 및 정확히 대응하는 업비트 자료. EXPLORATORY.\n\n"
    report += f"이 배치 조건 수: {len(rows)}. 원장은 실제 관측 분봉의 다음 연속 봉 시가 대용이며 실제 호가 체결 검증 결과가 아닙니다.\n\n"
    report += "기준 순위는 편도·레그별 2bp와 600_PLUS_CLEARING_ASSUMED입니다. 다른 비용·봉당 1세트 민감도는 별도 그룹입니다.\n\n"
    report += "계약·자금·증거금 입장 거절은 비활성화되어 가상 현금장부가 음수가 되어도 진입합니다. 필요한 자금은 별도 위험값으로 기록합니다. 실제 대출·차입·주문은 하지 않습니다.\n\n"
    report += "MDD 원화는 현금장부 기준 전체 손익의 관측 고점 대비 하락액이며 원금 비율이 아닙니다. completed_cycle_mdd_pp는 완료 사이클 수익률 누적선의 낙폭으로, 장중 위험을 대신하지 않습니다. 최대 평가손실은 미청산 세트의 현물·선물 누적 손익에서 이미 지불한 비용을 뺀 값의 최저점입니다. 미청산 평가손익에는 예상 청산비용도 별도 차감합니다.\n\n"
    report += "raw 원장 숫자 row_index는 source_timestamp_index.csv의 원본 KST 시각에 대응합니다. code 1/2는 진입/청산, 3/4는 롤오버 청산/재진입, 5는 공식 정산 변동금입니다. 평가손실 통계는 별도 risk mark에서 계산하며 code 5 자체를 미실현손익으로 오인하지 않습니다.\n\n"
    if best:
        report += "배치 최고 조건:\n\n```json\n" + json.dumps(best, ensure_ascii=False, indent=2) + "\n```\n"
    report += "\n상위 후보는 탐색 표본에서 선택된 것으로 독립 Final OOS 성과가 아닙니다. 역배는 USDT 차입 검증이 없는 이론값이며, 잔여 손실은 누적 완료 수익률에 숨겨 합산하거나 제거하지 않습니다.\n"
    (batch / "REPORT_KO.md").write_text(report, encoding="utf-8")
    source = STORAGE.project / "engine"
    for name in ("build_unlimited_engine.py", "unlimited_risk.py", "unlimited_execution.py", "unlimited_metrics.py", "unlimited_batch_io.py", "package_revalidation_batch.py", "run_unlimited_sweep.py", "test_unlimited_execution.py"):
        shutil.copyfile(source / name, batch / name)
    shutil.copyfile(batch.parent / "preregistration.json", batch / "preregistration.json")
    shutil.copyfile(batch.parent / "engine_unlimited_generated.py", batch / "engine_unlimited_generated.py")
    shutil.copyfile(batch.parent / "engine_unlimited_generated.audit.json", batch / "engine_unlimited_generated.audit.json")
    shutil.copyfile(batch.parent / "source_timestamp_index.csv.gz", batch / "source_timestamp_index.csv.gz")
    return finalize(batch)
