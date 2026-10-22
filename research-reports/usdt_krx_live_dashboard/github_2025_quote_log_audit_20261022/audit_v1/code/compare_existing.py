# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: python -B code/compare_existing.py after audit_logs.py.
from __future__ import annotations
import collections,datetime as dt,json,statistics
from audit_common import ROOT,PUBLIC,LOCAL,ARCH,sha,read_csv,table,save

def quantile(values:list[float],q:float)->float:
    """Linear empirical quantile, without modifying the original observations."""
    ordered=sorted(values);position=(len(ordered)-1)*q;lower=int(position);upper=min(lower+1,len(ordered)-1)
    return ordered[lower]+(ordered[upper]-ordered[lower])*(position-lower)

def main()->None:
    references=[]
    krx_path=ARCH/'krx_2025_full_1m/KRX_USD_1m_2025_01_01_to_2025_12_31.csv'
    krows=read_csv(krx_path)
    assert all(r['trade_date'].startswith('2025') for r in krows)
    krx={dt.datetime.strptime(r['trade_date']+r['time_kst'],'%Y%m%d%H%M%S').isoformat():r for r in krows}
    assert len(krx)==len(krows)
    references.append(dict(role='KRX_REGULAR_1M',path=str(krx_path),bytes=krx_path.stat().st_size,sha256=sha(krx_path.read_bytes()),rows=len(krows)))
    contract_path=ARCH/'krx_2025_full_1m/contract_selection.csv'
    official={r['date']:r for r in read_csv(contract_path) if r['date'].startswith('2025')}
    references.append(dict(role='KRX_CONTRACT_TRADING_CALENDAR',path=str(contract_path),bytes=contract_path.stat().st_size,sha256=sha(contract_path.read_bytes()),rows=len(official)))
    upbit={}
    for month in (10,11,12):
        path=ARCH/f'archive_2025_2026/upbit/monthly/upbit_krw_usdt_1m_2025-{month:02}.csv'
        rows=read_csv(path)
        assert all(r['candle_date_time_kst'].startswith('2025') for r in rows)
        upbit.update({r['candle_date_time_kst']:r for r in rows})
        references.append(dict(role='UPBIT_OHLCV_NOT_QUOTE',path=str(path),bytes=path.stat().st_size,sha256=sha(path.read_bytes()),rows=len(rows)))
    differences=collections.defaultdict(list);daily=[];matched=collections.Counter();local_records=[]
    for path in sorted((LOCAL/'normalized').glob('future_result_2025-*.txt.jsonl')):
        day=path.name[len('future_result_'):len('future_result_')+10]
        daykey=day.replace('-','');counts=collections.Counter();valid=[]
        with path.open(encoding='utf8') as f:
            for line in f:
                record=json.loads(line);values={p['raw_label']:p['value'] for p in record['fields']}
                if not all(values.get(k,0)>0 for k in ('USDT 매수가','USDT 매도가','선물 매수가','선물 매도가')):continue
                stamp=dt.datetime.fromisoformat(record['timestamp']);valid.append(stamp)
                counts['complete_pairs']+=1
                if daykey not in official:counts['pairs_on_nonofficial_regular_date_if_kst']+=1
                if not (dt.time(8,45)<=stamp.time()<=dt.time(15,45)):counts['outside_current_regular_envelope_if_kst']+=1
                if stamp.time()>=dt.time(18) or stamp.time()<=dt.time(6):counts['night_clock_labels_unverified']+=1
                if day<'2025-10-01':continue
                for label,value in values.items():
                    target=krx.get(stamp.isoformat()) if label.startswith('선물') else upbit.get(stamp.isoformat())
                    if target is None:continue
                    fields=('open','close') if label.startswith('선물') else ('opening_price','trade_price')
                    for field in fields:
                        diff=value-float(target[field]);key=(day[:7],label,field)
                        differences[key].append(diff);matched[key]+=1
                        local_records.append(dict(source_file=record['source_file'],source_line=record['line_start'],timestamp=record['timestamp'],raw_label=label,quote_value=value,reference_field=field,reference_value=float(target[field]),difference_krw=diff,reference_contract=target.get('contract_code_kis','KRW-USDT'),identity_confirmed=False,time_alignment='CONDITIONAL_SAME_LABEL_ASSUMING_KST_NOT_TRADE_TIME_VERIFICATION'))
        selected=official.get(daykey,{})
        daily.append(dict(date=day,complete_pairs=counts['complete_pairs'],first_complete_pair=min(valid).isoformat() if valid else '',last_complete_pair=max(valid).isoformat() if valid else '',official_regular_trading_date=daykey in official,reference_contract_not_log_verified=selected.get('contract_code_kis',''),reference_expiry_not_log_verified=selected.get('expiry_date',''),pairs_on_nonofficial_regular_date_if_kst=counts['pairs_on_nonofficial_regular_date_if_kst'],outside_current_regular_envelope_if_kst=counts['outside_current_regular_envelope_if_kst'],night_clock_labels_unverified=counts['night_clock_labels_unverified'],calendar_interpretation='CONDITIONAL_ONLY_TIMEZONE_UNCONFIRMED'))
    summary=[]
    for (month,label,field),values in sorted(differences.items()):
        summary.append(dict(month=month,raw_label=label,reference_field=field,n=len(values),mean_difference_krw=statistics.mean(values),median_difference_krw=statistics.median(values),p01_difference_krw=quantile(values,.01),p99_difference_krw=quantile(values,.99),minimum_difference_krw=min(values),maximum_difference_krw=max(values),mean_absolute_difference_krw=statistics.mean(abs(x) for x in values),exact_equal_count=sum(abs(x)<1e-8 for x in values),identity_confirmed=False,alignment='HYPOTHETICAL_KST_SAME_LABEL_ONLY',same_observation_type=False))
    table(LOCAL/'cross_comparison_rows.csv',local_records)
    table(PUBLIC/'cross_comparison_distribution.csv',summary)
    table(PUBLIC/'calendar_session_checks.csv',daily)
    table(PUBLIC/'reference_input_hashes.csv',references)
    save(PUBLIC/'cross_comparison_limitations.json',dict(krx_reference_bars=len(krx),upbit_reference_bars=len(upbit),same_type_historical_orderbook_compared=False,quote_exchange_confirmed=False,quote_contract_confirmed=False,timezone_confirmed=False,merged_series_created=False,statement='Differences are descriptive conditional comparisons, not accuracy certification. No prices from third-party logs are publicly redistributed.'))
    print(json.dumps(dict(comparison_groups=len(summary),conditional_price_comparisons=len(local_records),future_price_days=len([r for r in daily if r['complete_pairs']]),nonofficial_date_price_days=sum(r['complete_pairs']>0 and not r['official_regular_trading_date'] for r in daily),night_label_complete_pairs=sum(r['night_clock_labels_unverified'] for r in daily))))

if __name__=='__main__':main()
