# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
# Clarify ranking/inventory distinction, preserving financial output bytes.
from __future__ import annotations
import csv,json,shutil
from runner import ROOT,table,write_json
out=ROOT/"publish_payloads/final_structural_499_audit_stop_v1"
source=out/"ranking_unique_499.csv"
inventory=out/"all_unique_rules_499.csv"
assert not inventory.exists()
source.rename(inventory)
with inventory.open(encoding="utf8",newline="") as stream:rows=list(csv.DictReader(stream))
completed=[r for r in rows if int(r["cycles"])>0]
assert len(rows)==499 and len(completed)==455
table(out/"ranking_completed_unique.csv",[dict(rank=i+1,**r) for i,r in enumerate(completed)])
write_json(out/"ranking_definition.json",dict(inventory_rules=499,ranked_completed_rules=455,zero_completed_excluded=44,
    duplicate_id_excluded="SR-09-005",primary="ranking_completed_unique.csv",score="unrounded sum of net completed cycle return pct",
    funds_eligibility="separate columns and top20_margin_free.csv; no capital/absolute profit sorting"))
report=(out/"REPORT_KO.md").read_text(encoding="utf8")
report=report.replace("ranking_unique_499.csv에서중복ID를제외했습니다","all_unique_rules_499.csv에서중복ID를제외하고 ranking_completed_unique.csv에서는0완료44개도제외했습니다")
(out/"REPORT_KO.md").write_text(report,encoding="utf8")
readme=(out/"README_REPRODUCE_KO.md").read_text(encoding="utf8")
readme+="\n주순위 ranking_completed_unique.csv는455개완료규칙만점수순정렬했고0완료44개를제외합니다. all_unique_rules_499.csv는중복제외499개전체목록이며순위파일과구분합니다.\n"
(out/"README_REPRODUCE_KO.md").write_text(readme,encoding="utf8")
for path in (ROOT/"logs").glob("audit_final_metrics_[0-9]*.err"):
    shutil.copy2(path,out/"validation/original_uniqueness_failure_trace.txt")
shutil.copy2(ROOT/"operations/publication_addendum.py",out/"operations/publication_addendum.py")
print("RANKING_455_COMPLETED_UNIQUE_ZERO_EXCLUDED")
