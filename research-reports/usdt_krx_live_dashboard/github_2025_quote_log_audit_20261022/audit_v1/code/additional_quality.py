# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: python -B code/additional_quality.py after the two audits.
import collections,datetime as dt,json,re
from quote_parser import ERROR_PATTERNS
from audit_common import ROOT,PUBLIC,LOCAL,table,read_csv,save,sha

def main()->None:
    daily=read_csv(PUBLIC/'daily_coverage.csv')
    sessions=read_csv(PUBLIC/'calendar_session_checks.csv')
    hours=[];raw_ranges=[];suspicious=[];unclassified=[]
    for path in sorted((LOCAL/'normalized').glob('future_result_2025-*.txt.jsonl')):
        counts=collections.Counter();first=None;last=None
        with path.open(encoding='utf8') as f:
            for line in f:
                r=json.loads(line);v={x['raw_label']:x['value'] for x in r['fields']}
                if not all(v.get(k,0)>0 for k in ('USDT 매수가','USDT 매도가','선물 매수가','선물 매도가')):continue
                stamp=dt.datetime.fromisoformat(r['timestamp']);counts[stamp.strftime('%H')]+=1
                first=stamp if first is None else min(first,stamp);last=stamp if last is None else max(last,stamp)
        for hour,n in sorted(counts.items()):hours.append(dict(source_file=path.name[:-6],date=path.name[14:24],clock_hour=hour,complete_pair_observations=n,timezone='UNCONFIRMED'))
        raw_ranges.append(dict(source_file=path.name[:-6],first=first.isoformat() if first else '',last=last.isoformat() if last else '',complete_pair_observations=sum(counts.values()),night_clock_labels=sum(n for h,n in counts.items() if int(h)>=18 or int(h)<6),timezone='UNCONFIRMED',session_assignment='NOT_ESTABLISHED'))
    for r in daily:
        if float(r['max_identical_quote_run_calendar_minutes'])>=30:
            suspicious.append(dict(path=r['path'],kind=r['kind'],date=r['date'],max_identical_quote_run_calendar_minutes=r['max_identical_quote_run_calendar_minutes'],action='FLAGGED_RETAINED_NOT_AUTOMATIC_ERROR'))
    for path in sorted((ROOT/'raw').glob('*/*.txt')):
        for number,line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
            if not line.strip():continue
            recognized=bool(re.search(r'^20\d{2}-|USDT 매수가|USDT 매도가|선물 매수가|선물 매도가|USD \(원화\)|퍼센티지|요청 실패|데이터가 없습니다|토큰|token|텔레그램|메시지',line,re.I))
            recognized=recognized or any(pattern.search(line) for _,pattern in ERROR_PATTERNS)
            if not recognized:unclassified.append(dict(path=path.name,line=number,message_sha256=sha(line.encode()),classification='UNCLASSIFIED_RETAINED_LOCAL'))
    monthly=[]
    for month in range(1,13):
        mm=f'2025-{month:02}';fr=[r for r in daily if r['kind']=='future' and r['month']==mm];sr=[r for r in daily if r['kind']=='spot' and r['month']==mm]
        calendar=[r for r in sessions if r['date'].startswith(mm)]
        hr=[r for r in hours if mm in r['source_file']]
        monthly.append(dict(month=mm,target_files=len(fr)+len(sr),downloaded_files=len(fr)+len(sr),future_files=len(fr),related_spot_files=len(sr),future_price_days=sum(int(r['valid_price_observations'])>0 for r in fr),complete_pair_days=sum(int(r['complete_pair_count'])>0 for r in fr),complete_pair_observations=sum(int(r['complete_pair_count']) for r in fr),partial_price_observations=sum(int(r['valid_price_observations'])-int(r['complete_pair_count']) for r in fr),future_error_lines=sum(int(r['errors']) for r in fr),related_spot_error_lines=sum(int(r['errors']) for r in sr),first_price=min((r['first_price'] for r in fr if r['first_price']),default=''),last_price=max((r['last_price'] for r in fr if r['last_price']),default=''),night_clock_observations=sum(int(r['night_clock_labels_unverified']) for r in calendar),price_days_not_official_regular_date_if_kst=sum(int(r['complete_pairs'])>0 and r['official_regular_trading_date']=='False' for r in calendar),contract='UNCONFIRMED',regular_night='LOG_CLOCK_ONLY_TZ_UNCONFIRMED',decision='가격은 있으나 출처/월물/시간 미확인'))
    error_only=[r for r in daily if r['kind']=='future' and int(r['valid_price_observations'])==0]
    table(PUBLIC/'results.csv',monthly);table(PUBLIC/'hourly_clock_coverage.csv',hours);table(PUBLIC/'date_time_coverage.csv',raw_ranges)
    table(PUBLIC/'stale_quote_flags.csv',suspicious);table(PUBLIC/'error_only_future_dates.csv',error_only);table(PUBLIC/'unclassified_lines.csv',unclassified)
    summary=dict(future_files=sum(r['future_files'] for r in monthly),related_spot_files=sum(r['related_spot_files'] for r in monthly),future_price_days=sum(r['future_price_days'] for r in monthly),future_complete_pairs=sum(r['complete_pair_observations'] for r in monthly),future_partial_prices=sum(r['partial_price_observations'] for r in monthly),jan_sep_price_days=sum(r['future_price_days'] for r in monthly[:9]),jan_sep_complete_pairs=sum(r['complete_pair_observations'] for r in monthly[:9]),error_only_future_days=len(error_only),error_only_dates=[r['date'] for r in error_only],duplicate_timestamp_blocks=sum(int(r['duplicate_timestamp_blocks']) for r in daily),conflicting_timestamp_labels=sum(int(r['conflicting_timestamp_labels']) for r in daily),unparsed_price_lines=sum(int(r['unparsed_price_lines']) for r in daily),filename_date_mismatch_blocks=sum(int(r['filename_date_mismatch_blocks']) for r in daily),nonpositive_prices=sum(int(r['nonpositive_prices']) for r in daily),sensitive_pattern_hits=sum(int(r['sensitive_pattern_hits']) for r in read_csv(PUBLIC/'identity_and_sensitive_scan.csv')),stale_quote_flagged_files=len(suspicious),unclassified_lines=len(unclassified),price_days_not_official_regular_date_if_kst=sum(r['price_days_not_official_regular_date_if_kst'] for r in monthly),night_clock_observations=sum(r['night_clock_observations'] for r in monthly),B_validation_eligible_period='NONE_IDENTITY_TIME_CONTRACT_UNCONFIRMED',full_year_validation_ready=False)
    save(PUBLIC/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
