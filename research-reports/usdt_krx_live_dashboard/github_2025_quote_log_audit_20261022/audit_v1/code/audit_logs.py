# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: python -B code/audit_logs.py from the frozen D: study.
from __future__ import annotations
import collections,datetime as dt,hashlib,json,re,statistics
from dataclasses import asdict
from audit_common import ROOT,PUBLIC,LOCAL,sha,table,save
from quote_parser import parse_log,parser_regression_checks,KEYS

def main()->None:
    tests=parser_regression_checks()
    source=json.loads((ROOT/'metadata/source_tree.json').read_text(encoding='utf8'))
    inventory=json.loads((ROOT/'metadata/download_inventory.json').read_text(encoding='utf8'))
    assert source['truncated'] is False
    daily=[];field_rows=[];error_rows=[];gaps=[];segments=[];source_findings=[];coverage=[];independent=[]
    normalized=LOCAL/'normalized';normalized.mkdir(exist_ok=True)
    labels=collections.Counter();all_errors=collections.Counter()
    for month in range(1,13):
        mm=f'2025-{month:02}'
        for item in [x for x in inventory if x['month']==mm]:
            if not item['downloaded']:continue
            path=ROOT/'raw'/mm/item['path'];b=path.read_bytes()
            assert len(b)==item['bytes'] and sha(b)==item['sha256']
            assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==item['blob_sha']
            text=b.decode('utf-8-sig');parsed=parse_log(text)
            kind=item['path'].split('_')[0];filename_day=item['path'][-14:-4]
            observations=[o for o in parsed.observations if o.timestamp.year==2025 and o.timestamp.date().isoformat()==filename_day]
            excluded=len(parsed.observations)-len(observations)
            prices=[o for o in observations if o.has_price];full=[o for o in observations if o.complete_pair]
            counts=collections.Counter(o.timestamp for o in observations)
            complete_times=sorted(set(o.timestamp for o in full))
            any_times=sorted(set(o.timestamp for o in prices))
            conflicts=0
            by_time=collections.defaultdict(set)
            for o in prices:by_time[o.timestamp].add(tuple(sorted(o.values().items())))
            conflicts=sum(len(v)>1 for v in by_time.values())
            duplicate_labels=sum(len(o.fields)-len(o.values()) for o in observations)
            invalid=sum(p.value<=0 for o in observations for p in o.fields)
            errors=collections.Counter(e.category for e in parsed.errors);all_errors.update(errors)
            raw_price_count=sum(len(re.findall(r'(?:USDT 매수가|USDT 매도가|선물 매수가|선물 매도가|USD \(원화\))\s*:\s*[-+]?\d[\d,]*(?:\.\d+)?',line)) for line in text.splitlines())
            parsed_price_count=sum(len(o.fields) for o in parsed.observations)
            assert raw_price_count==parsed_price_count
            independent.append(dict(path=item['path'],raw_price_occurrences=raw_price_count,parsed_price_occurrences=parsed_price_count,passed=True))
            with (normalized/(item['path']+'.jsonl')).open('w',encoding='utf8') as output:
                for o in observations:
                    record=asdict(o);record['timestamp']=o.timestamp.isoformat();record.update(source_file=item['path'],source_sha256=item['sha256'],source_commit=item['source_commit'],timezone='UNCONFIRMED',quote_timestamp='UNCONFIRMED',exchange='UNCONFIRMED',contract='UNCONFIRMED',raw_label_mapping='UNCONFIRMED')
                    output.write(json.dumps(record,ensure_ascii=False)+'\n')
                    for p in o.fields:labels[p.raw_label]+=1
            # Individual errors stay local; published classifications carry source line and message hash only.
            for e in parsed.errors:
                error_rows.append(dict(source_file=item['path'],line=e.line_number,category=e.category,message_sha256=sha(e.raw_message.encode())))
            # Only within-observed-window gaps; never label outside this window as missed market trading.
            times=complete_times if kind=='future' else any_times
            segment_start=times[0] if times else None;previous=None;longest_stale=0;stale_start=None;stale_signature=None
            for stamp in times:
                if previous is not None and (stamp-previous).total_seconds()>60:
                    gaps.append(dict(source_file=item['path'],previous=previous.isoformat(),next=stamp.isoformat(),elapsed_minutes=(stamp-previous).total_seconds()/60,unobserved_minute_labels=int((stamp-previous).total_seconds()/60)-1,status='UNOBSERVED_NOT_CONFIRMED_TRADING_GAP'))
                    segments.append(dict(source_file=item['path'],first=segment_start.isoformat(),last=previous.isoformat(),calendar_minutes=(previous-segment_start).total_seconds()/60+1))
                    segment_start=stamp
                previous=stamp
            if times:segments.append(dict(source_file=item['path'],first=segment_start.isoformat(),last=times[-1].isoformat(),calendar_minutes=(times[-1]-segment_start).total_seconds()/60+1))
            for o in prices:
                signature=tuple(sorted(o.values().items()))
                if signature!=stale_signature:stale_start=o.timestamp;stale_signature=signature
                if stale_start is not None:longest_stale=max(longest_stale,(o.timestamp-stale_start).total_seconds()/60)
            evidence={term:len(re.findall(term,text,re.I)) for term in ('업비트','upbit','빗썸','bithumb','KRX','미국달러','175[A-Z0-9]{3,6}','A75[A-Z0-9]{3,5}','KST','UTC','Asia/Seoul')}
            sensitive=len(re.findall(r'(?:appkey|appsecret|access_token|secretkey|account_no|CANO)\s*[\"\':= ]+([A-Za-z0-9+/_=-]{16,})|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|\b\d{8,12}:[A-Za-z0-9_-]{30,}',text,re.I))
            source_findings.append(dict(source_file=item['path'],identity_term_counts=json.dumps(evidence,ensure_ascii=False),sensitive_pattern_hits=sensitive,timezone='UNCONFIRMED',contract='UNCONFIRMED',exchange='UNCONFIRMED'))
            row=dict(month=mm,kind=kind,date=filename_day,path=item['path'],downloaded=True,has_price=bool(prices),complete_pair_count=len(full),valid_price_observations=len(prices),timestamp_blocks=len(observations),unique_timestamp_labels=len(counts),first_record=observations[0].raw_timestamp if observations else '',last_record=observations[-1].raw_timestamp if observations else '',first_price=prices[0].raw_timestamp if prices else '',last_price=prices[-1].raw_timestamp if prices else '',errors=sum(errors.values()),error_categories=json.dumps(errors,ensure_ascii=False),duplicate_timestamp_blocks=sum(n-1 for n in counts.values()),conflicting_timestamp_labels=conflicts,duplicate_labels_within_block=duplicate_labels,nonpositive_prices=invalid,time_reversals=sum(b.timestamp<a.timestamp for a,b in zip(observations,observations[1:])),filename_date_mismatch_blocks=excluded,unparsed_price_lines=len(parsed.unparsed_price_lines),orphan_lines=len(parsed.orphan_content_lines),max_identical_quote_run_calendar_minutes=longest_stale,session='LOCAL_LABEL_ONLY_TZ_UNCONFIRMED',contract='UNCONFIRMED',exchange='UNCONFIRMED',eligibility='PRICE_PRESENT_IDENTITY_UNCONFIRMED' if prices else 'ERROR_OR_EMPTY_NO_PRICE')
            daily.append(row)
        month_rows=[r for r in daily if r['month']==mm]
        table(PUBLIC/f'daily_{mm}.csv',month_rows)
        print(json.dumps(dict(month=mm,downloaded=len(month_rows),future_price_days=sum(r['kind']=='future' and r['has_price'] for r in month_rows),future_complete_pairs=sum(r['complete_pair_count'] for r in month_rows if r['kind']=='future'),error_lines=sum(r['errors'] for r in month_rows)),ensure_ascii=False),flush=True)
    monthly=[]
    for month in range(1,13):
        mm=f'2025-{month:02}'
        for kind in ('future','spot'):
            selected=[r for r in daily if r['month']==mm and r['kind']==kind]
            targets=[r for r in inventory if r['month']==mm and r['path'].startswith(kind+'_')]
            monthly.append(dict(month=mm,kind=kind,target_files=len(targets),downloaded_files=len(selected),valid_price_days=sum(r['has_price'] for r in selected),complete_pair_days=sum(r['complete_pair_count']>0 for r in selected),valid_price_observations=sum(r['valid_price_observations'] for r in selected),complete_pair_observations=sum(r['complete_pair_count'] for r in selected),errors=sum(r['errors'] for r in selected),first_price=min((r['first_price'] for r in selected if r['first_price']),default=''),last_price=max((r['last_price'] for r in selected if r['last_price']),default=''),regular_night='TIMEZONE_SESSION_UNCONFIRMED',contract='UNCONFIRMED',eligibility='PRICE_PRESENT_IDENTITY_UNCONFIRMED' if any(r['has_price'] for r in selected) else 'ERROR_OR_EMPTY_NO_PRICE'))
    present={r['path'] for r in inventory}
    for offset in range(365):
        day=(dt.date(2025,1,1)+dt.timedelta(days=offset)).isoformat()
        for kind in ('future','spot'):
            name=f'{kind}_result_{day}.txt'
            coverage.append(dict(date=day,kind=kind,path=name,file_exists=name in present,missing_means='FILE_ABSENT_NOT_MARKET_GAP' if name not in present else 'PRESENT'))
    table(PUBLIC/'source_files.csv',inventory);table(PUBLIC/'daily_coverage.csv',daily);table(PUBLIC/'monthly_coverage.csv',monthly)
    table(PUBLIC/'calendar_file_coverage.csv',coverage);table(PUBLIC/'missing_files.csv',[r for r in coverage if not r['file_exists']])
    table(PUBLIC/'error_classification.csv',error_rows);table(PUBLIC/'observation_gaps.csv',gaps);table(PUBLIC/'continuous_segments.csv',segments)
    table(PUBLIC/'identity_and_sensitive_scan.csv',source_findings);table(PUBLIC/'parser_independent_count_check.csv',independent)
    save(PUBLIC/'validation.json',dict(source_commit=source['sha'],tree_truncated=False,inventory_files=len(inventory),downloaded_files=sum(r['downloaded'] for r in inventory),original_bytes=sum(r['bytes'] for r in inventory if r['downloaded']),synthetic_parser_assertions=tests,independent_file_parse_checks=len(independent),all_byte_sha_and_blob_checks=True,raw_labels=dict(labels),errors=dict(all_errors),raw_or_normalized_redistributed=False,backtest_run=False,protected_oos_read=False,source_code_executed=False))

if __name__=='__main__':main()
