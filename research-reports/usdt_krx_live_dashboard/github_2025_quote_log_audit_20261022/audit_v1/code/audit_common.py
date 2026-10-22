# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: helper imported by local audit modules.
import csv,json,hashlib
from pathlib import Path
from typing import Mapping,Sequence
ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'publish_payload';PUBLIC.mkdir(exist_ok=True)
LOCAL=ROOT/'derived_local';LOCAL.mkdir(exist_ok=True)
ARCH=Path(r'D:/Codex_Research/archive/c_drive_migration_20261020/codex_workspace/files-pasted-by-the-user-codex/outputs/usdt_krx_live_dashboard/data')
Scalar=str|int|float|bool|None

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def read_csv(p:Path)->list[dict[str,str]]:
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def table(path:Path,rows:Sequence[Mapping[str,Scalar]],fields:Sequence[str]|None=None)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    columns=list(fields) if fields else list(rows[0]) if rows else ['status']
    with path.open('w',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerows(rows)
def save(path:Path,value:Mapping)->None:path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
