# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: python -B code/bootstrap.py prepare_quotes.py
from __future__ import annotations
import collections,datetime as dt,json
from common import ROOT,SOURCE,LOCAL,OUT,ARCH,sha,read_csv,table,save


def main()->None:
    checks=[]
    for row in read_csv(SOURCE/'publish_payload/manifest.csv'):
        path=SOURCE/'publish_payload'/row['path'];b=path.read_bytes()
        assert len(b)==int(row['bytes']) and sha(b)==row['sha256']
        checks.append(dict(kind='AUDIT_CODE_AND_REPORT',path=str(path),bytes=len(b),sha256=sha(b),passed=True))
    for row in read_csv(SOURCE/'publish_payload/local_artifact_hashes.csv'):
        path=SOURCE/row['path'];b=path.read_bytes()
        assert len(b)==int(row['bytes']) and sha(b)==row['sha256']
        checks.append(dict(kind='RAW_OR_NORMALIZED_LOCAL',path=str(path),bytes=len(b),sha256=sha(b),passed=True))
    table(OUT/'input_integrity.csv',checks)
    official={r['date']:r for r in read_csv(ARCH/'krx_2025_full_1m/contract_selection.csv') if r['date'].startswith('2025')}
    quotes=[];excluded=[];all_full=[];duplicates=[]
    for path in sorted((SOURCE/'derived_local/normalized').glob('future_result_2025-*.txt.jsonl')):
        with path.open(encoding='utf8') as f:
            for line in f:
                r=json.loads(line);t=dt.datetime.fromisoformat(r['timestamp'])
                assert t.year==2025
                v={p['raw_label']:p['value'] for p in r['fields']};reasons=[]
                keys=('USDT 매수가','USDT 매도가','선물 매도가','선물 매수가')
                if not all(v.get(k,0)>0 for k in keys):reasons.append('INCOMPLETE_OR_NONPOSITIVE')
                day=t.strftime('%Y%m%d');ref=official.get(day)
                if ref is None:reasons.append('NOT_OFFICIAL_REGULAR_DATE')
                if not dt.time(8,45)<=t.time()<=dt.time(15,45):reasons.append('NIGHT_OR_OUTSIDE_ASSUMED_REGULAR')
                if ref and t.date().isoformat()==ref['expiry_date'] and t.time()>dt.time(11,30):reasons.append('REFERENCED_EXPIRY_AFTER_1130')
                if all(v.get(k,0)>0 for k in keys):
                    if v['USDT 매수가']<v['USDT 매도가'] or v['선물 매도가']<v['선물 매수가']:reasons.append('CROSSED_ASSUMED_QUOTES')
                    all_full.append(dict(t=t.isoformat(),spot_mid=(v['USDT 매수가']+v['USDT 매도가'])/2,future_mid=(v['선물 매도가']+v['선물 매수가'])/2,source=r['source_file'],line=r['line_start']))
                if reasons:
                    excluded.append(dict(t=t.isoformat(),source_file=r['source_file'],line_start=r['line_start'],reasons=';'.join(reasons)));continue
                quotes.append(dict(t=t.isoformat(),sa=v['USDT 매수가'],sb=v['USDT 매도가'],fa=v['선물 매도가'],fb=v['선물 매수가'],gap=100*((v['USDT 매수가']+v['USDT 매도가'])/(v['선물 매도가']+v['선물 매수가'])-1),source=r['source_file'],line=r['line_start'],source_sha256=r['source_sha256'],reference_contract=ref['contract_code_kis'],contract_verified=False,timezone_verified=False))
    grouped=collections.defaultdict(list)
    for q in quotes:grouped[q['t']].append(q)
    cleaned=[]
    for t,rows in sorted(grouped.items()):
        signatures={tuple(r[k] for k in ('sa','sb','fa','fb')) for r in rows}
        if len(signatures)>1:
            for r in rows:excluded.append(dict(t=t,source_file=r['source'],line_start=r['line'],reasons='CONFLICTING_DUPLICATE_TIMESTAMP'))
            duplicates.append(dict(t=t,count=len(rows),resolution='EXCLUDE_ALL_CONFLICTS'));continue
        cleaned.append(rows[0])
        if len(rows)>1:duplicates.append(dict(t=t,count=len(rows),resolution='COLLAPSE_EXACT_WITH_PROVENANCE'))
    segments=[];boundaries=[];current=[]
    for q in cleaned:
        if current:
            p=current[-1];a=dt.datetime.fromisoformat(p['t']);b=dt.datetime.fromisoformat(q['t']);reason=''
            if p['reference_contract']!=q['reference_contract']:reason='ROLL_REFERENCE_CHANGE_UNVERIFIED_PRICES'
            elif a.date()!=b.date():reason='SESSION_BOUNDARY_OVERNIGHT_UNOBSERVED'
            elif (b-a).total_seconds()!=60:reason='MISSING_OR_INVALID_PRICE_INTERVAL'
            if reason:
                segments.append(current);boundaries.append(dict(before=p['t'],after=q['t'],reason=reason,elapsed_minutes=(b-a).total_seconds()/60,old_reference=p['reference_contract'],new_reference=q['reference_contract'],future_mid_jump_krw=(q['fa']+q['fb']-p['fa']-p['fb'])/2,reference_contract_only=True));current=[]
        current.append(q)
    if current:segments.append(current)
    with (LOCAL/'segments.jsonl').open('x',encoding='utf8') as f:
        for i,rows in enumerate(segments):
            for q in rows:q['segment']=i+1
            f.write(json.dumps(dict(segment=i+1,quotes=rows,end_reason=boundaries[i]['reason'] if i<len(boundaries) else 'DATA_END_UNOBSERVED_AFTER_LAST_QUOTE'),ensure_ascii=False)+'\n')
    table(OUT/'exclusions.csv',excluded);table(OUT/'duplicate_resolution.csv',duplicates);table(OUT/'boundary_jumps.csv',boundaries)
    table(OUT/'segments.csv',[dict(segment=i+1,first=s[0]['t'],last=s[-1]['t'],observations=len(s),reference_contract=s[0]['reference_contract'],end_reason=boundaries[i]['reason'] if i<len(boundaries) else 'DATA_END_UNOBSERVED_AFTER_LAST_QUOTE',identity='ASSUMED_NOT_VERIFIED') for i,s in enumerate(segments)])
    monthly=[]
    for m in range(1,13):
        prefix=f'2025-{m:02}'
        rs=[q for q in cleaned if q['t'].startswith(prefix)]
        monthly.append(dict(month=prefix,eligible_observations=len(rs),observation_days=len({q['t'][:10] for q in rs}),segments=sum(s[0]['t'].startswith(prefix) for s in segments),excluded_blocks=sum(q['t'].startswith(prefix) for q in excluded),first=rs[0]['t'] if rs else '',last=rs[-1]['t'] if rs else '',confirmed_product_contract_timezone=False))
    table(OUT/'monthly_input.csv',monthly)
    save(OUT/'preparation.json',dict(input_hash_checks=len(checks),all_pass=True,eligible_observations=len(cleaned),segments=len(segments),excluded_blocks=len(excluded),no_interpolation=True,original_modified=False,reference_contracts_only=True,complete_year_continuity=False))
    print(json.dumps(dict(stage='PREPARATION_PASS',observations=len(cleaned),segments=len(segments),hash_checks=len(checks))))

if __name__=='__main__':main()
