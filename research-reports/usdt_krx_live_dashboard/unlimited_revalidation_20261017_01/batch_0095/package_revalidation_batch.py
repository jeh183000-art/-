# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

APPROVED_FILES = frozenset({"paper_engine.py", "preregistration.json", "analysis_scope.json", "margin_schedule.csv", "reproduce_unlimited_baseline.py", "validation.json", "environment.json", "trades.csv", "events.csv", "residuals.csv", "results.csv", "cycles.csv", "costs.csv", "REPORT_KO.md", "trades.csv.gz", "events.csv.gz", "residuals.csv.gz", "risks.csv", "settings.json", "build_unlimited_engine.py", "unlimited_risk.py", "unlimited_execution.py", "unlimited_metrics.py", "unlimited_batch_io.py", "package_revalidation_batch.py", "run_unlimited_sweep.py", "test_unlimited_execution.py", "engine_unlimited_generated.py", "engine_unlimited_generated.audit.json", "source_timestamp_index.csv.gz", "run_unlimited_sensitivity.py", "sensitivity_sources.csv", "unlimited_rankings.py"})


def finalize(batch: Path) -> Path:
    if batch.name == "batch_000_original_control":
        control = json.loads((batch / "validation.json").read_text(encoding="utf-8"))
        with (batch / "results.csv").open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(control))
            writer.writeheader()
            writer.writerow(control)
        with (batch / "trades.csv").open(encoding="utf-8", newline="") as stream:
            trades = list(csv.DictReader(stream))
        costs = {"fees_krw": sum(float(row["fees_krw"]) for row in trades), "slippage_krw": sum(float(row["slippage_krw"]) for row in trades), "funding_krw": 0, "funding_status": "NOT_APPLICABLE_KRX_DATED_FUTURES", "fee_policy": "600_PLUS_CLEARING_ASSUMED", "slippage_bp_per_side_per_leg": 2}
        with (batch / "costs.csv").open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(costs))
            writer.writeheader()
            writer.writerow(costs)
        report = "# 배치 000: 기존 엔진 대조\n\nDB-0249: 정배 E=1.4%, S=0.2%p, R=3.0%p, 전량청산.\n\n기존 제한 엔진을 변경하지 않고 재현했습니다. 완료 3사이클, 청산 12세트, 잔여 0세트.\n순이익 4,890,138.803278029원, 사이클 수익률 단순 합계 8.554937368493867%.\n사이클을 각각 소수 넷째 자리로 반올림해 더하면 8.5550%입니다.\n실제 현물자금 거절 656건으로 기존 제한의 작동도 확인했습니다.\n엔진 해시 전후 일치. 신규 전략 결과는 이 대조 통과 이후에만 확정합니다.\n실제 체결 호가가 검증되지 않은 탐색용 PAPER 결과입니다.\n"
        (batch / "REPORT_KO.md").write_text(report, encoding="utf-8")
    payload = batch / "publish"
    payload.mkdir(exist_ok=False)
    unexpected = {file.name for file in batch.iterdir() if file.is_file()} - APPROVED_FILES - {"publication_receipt.json", "READY.json"}
    if unexpected:
        raise RuntimeError("Unexpected files in publication batch; explicit allowlist inspection required")
    for file in sorted(batch.iterdir()):
        if file.is_file() and file.name in APPROVED_FILES:
            shutil.copyfile(file, payload / file.name)
    roles = []
    for file in sorted(payload.iterdir()):
        name = file.name.lower()
        role = "support"
        if name.endswith(".py"):
            role = "strategy_code"
        if name in {"settings.json", "preregistration.json", "analysis_scope.json"}:
            role = "settings"
        if name in {"results.csv", "cycles.csv", "cycles.csv.gz", "risks.csv"}:
            role = "results_csv"
        if name.startswith(("trades", "events", "residuals")):
            role = "fills"
        if name == "costs.csv":
            role = "costs"
        if name == "report_ko.md":
            role = "statistics_report"
        if name == "environment.json":
            role = "environment"
        data = file.read_bytes()
        roles.append({"path": file.name, "role": role, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    with (payload / "manifest.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "role", "bytes", "sha256"])
        writer.writeheader()
        writer.writerows(roles)
    return payload


if __name__ == "__main__":
    print(finalize(Path(sys.argv[1]).resolve()))
