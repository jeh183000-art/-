# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# How to run: imported by this fixed-rule quote-log PAPER study.
from pathlib import Path
import csv,hashlib,json
from typing import Mapping,Sequence
ROOT=Path(__file__).resolve().parents[1]
PRIOR=Path(r'D:/Codex_Research/usdt_krx_live_dashboard/studies/b_2025_quote_paper_20261022_11')
BOUNDARY=Path(r'D:/Codex_Research/usdt_krx_live_dashboard/studies/b_2025_regular_carry_paper_20261022_12')
SOURCE=Path(r'D:/Codex_Research/usdt_krx_live_dashboard/studies/github_2025_quote_log_audit_20261022/v1')
LOCAL=ROOT/'data_local';LOCAL.mkdir(exist_ok=True)
OUT=ROOT/'results';OUT.mkdir(exist_ok=True)
PUB=ROOT/'publish_payload';PUB.mkdir(exist_ok=True)
OLD=Path(r'D:/Codex_Research/usdt_krx_live_dashboard/studies/b_fixed_2025_validation_20261022_07/code')
ARCH=Path(r'D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/outputs/usdt_krx_live_dashboard/data')
Scalar=str|int|float|bool|None

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def read_csv(p:Path)->list[dict[str,str]]:
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def table(p:Path,rows:Sequence[Mapping],fields:Sequence[str]|None=None)->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    columns=list(fields) if fields else list(rows[0]) if rows else ['status']
    with p.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='raise');w.writeheader();w.writerows(rows)
def save(p:Path,data:Mapping)->None:p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
