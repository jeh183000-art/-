# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Metadata-only rule inventory; do not read OOS or market originals.
from __future__ import annotations
import csv, hashlib, json
from pathlib import Path
from typing import TypedDict
from runner import ROOT, canonical, table, write_json
from path_schema import PathRule

class SourceRecord(TypedDict):
    path: str
    sha256: str
    records: int
    format: str

KEYS=set(PathRule.__annotations__)
BASE: PathRule=json.loads((ROOT/'baseline/registry.json').read_text())['B']['rule']

def signature(value: PathRule) -> str:
    """Resolve inert defaults and equivalent symmetric/directional profit settings."""
    r={k:v for k,v in value.items() if k in KEYS and v is not None and v!=0}
    family=value.get('family','relative')
    if family in ('relative','reversal'):
        r['family']='relative'
    active=bool(value.get('confirmation_pp') or value.get('confirmation_min_observations'))
    if active:
        r['confirmation_expiry_calendar_minutes']=value.get('confirmation_expiry_calendar_minutes') or 240
    else:
        r.pop('confirmation_expiry_calendar_minutes',None)
    if value.get('slippage_bp',2)==2:
        r.pop('slippage_bp',None)
    if value.get('threshold_mode','fixed')=='fixed':
        for k in ('threshold_mode','window_observations','center_weight','volatility_entry_scale','volatility_recovery_scale'):
            r.pop(k,None)
    long=float(value.get('pnl_profit_long_pct',value.get('pnl_profit_pct') or 0))
    short=float(value.get('pnl_profit_short_pct',value.get('pnl_profit_pct') or 0))
    for k in ('pnl_profit_pct','pnl_profit_long_pct','pnl_profit_short_pct'):
        r.pop(k,None)
    if long:r['pnl_profit_long_pct']=long
    if short:r['pnl_profit_short_pct']=short
    if value.get('gap_exit_enabled',True):
        r.pop('gap_exit_enabled',None)
    else:
        r['gap_exit_enabled']='DISABLED'
    if value.get('allowed_direction')==1:
        r={k:v for k,v in r.items() if not k.startswith('short_') and k!='pnl_profit_short_pct'}
    if value.get('allowed_direction')==-1:
        r={k:v for k,v in r.items() if not k.startswith('long_') and k!='pnl_profit_long_pct'}
    r={k:(round(float(v),12) if isinstance(v,(int,float)) and not isinstance(v,bool) else v) for k,v in r.items()}
    return hashlib.sha256(canonical(r)).hexdigest()

def extract(value: list | dict) -> list[PathRule]:
    """Recognize explicit newer rules and original one-set legacy definitions."""
    rows=[]
    if isinstance(value,list):
        for item in value:
            if isinstance(item,(list,dict)):rows.extend(extract(item))
        return rows
    if 'family' in value and 'long_entry_gap_pct' in value:
        return [{k:v for k,v in value.items() if k in KEYS}]
    if 'family' in value and 'entry' in value and value['family'] in ('relative','reversal'):
        e=float(value['entry'])
        return [dict(family=value['family'],long_entry_gap_pct=-e,short_entry_gap_pct=e,
            long_recovery_pp=float(value.get('recovery') or 0),short_recovery_pp=float(value.get('recovery') or 0),
            allowed_direction=int(value.get('direction') or 0),confirmation_pp=float(value.get('confirm') or 0),
            pnl_profit_pct=float(value.get('pnl_profit') or 0),pnl_stop_pct=float(value.get('pnl_stop') or 0),
            max_hold_minutes=float(value.get('max_hold') or 0),gap_stop_pp=float(value.get('gap_stop') or 0),
            stall_minutes=float(value.get('stall') or 0))]
    for item in value.values():
        if isinstance(item,(list,dict)):rows.extend(extract(item))
    return rows

def inventory() -> set[str]:
    """Read declared rule tables across all existing project studies, not result/price trees."""
    sources=set()
    for study in ROOT.parent.iterdir():
        if not study.is_dir() or study==ROOT:continue
        for pattern in ('*settings*.json','*prereg*.json','*condition*.csv','*grid*.csv'):
            sources.update(study.glob(pattern))
        for directory in ('preregistration','preregistration_payload'):
            if (study/directory).is_dir():
                sources.update((study/directory).glob('*.json'))
                sources.update((study/directory).glob('*grid*.csv'))
    registry=json.loads((ROOT/'baseline/registry.json').read_text())
    sources.update(Path(x['path']) for x in registry['previous_rule_sources'])
    used=set();records: list[SourceRecord]=[]
    for path in sorted(sources):
        assert not any(x in path.name.lower() for x in ('oos','token','secret'))
        if path.suffix=='.json':
            rules=extract(json.loads(path.read_text(encoding='utf8')))
            used.update(signature(r) for r in rules)
            count=len(rules)
            kind='explicit single-bundle rules'
        else:
            with path.open(encoding='utf-8-sig',newline='') as stream:
                data=list(csv.DictReader(stream))
            rules=extract(data)
            used.update(signature(r) for r in rules)
            count=len(data)
            kind='legacy grid metadata; multi-stage grids are structurally distinct' if not rules else 'single-bundle CSV rules'
        records.append(SourceRecord(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),records=count,format=kind))
    used.add(signature(BASE))
    table(ROOT/'registry_sources.csv',records)
    write_json(ROOT/'registry_summary.json',dict(status='PASS_METADATA_ONLY',files=len(records),
        table_rows=sum(x['records'] for x in records),unique_single_bundle_rules=len(used),
        protected_oos_access=False,price_data_read=False,
        multi_stage_grids_distinct_from_no_add_bundle=True))
    return used
