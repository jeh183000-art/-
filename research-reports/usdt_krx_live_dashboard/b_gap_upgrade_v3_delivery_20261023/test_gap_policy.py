"""No user data required; run: python -B test_gap_policy.py"""
from dataclasses import dataclass
from datetime import datetime
from gap_policy import classify_boundary

@dataclass(frozen=True)
class Q:
    t: datetime
    reference_contract: str = '175W01'

def q(s: str, contract='175W01') -> Q:
    return Q(datetime.fromisoformat(s), contract)

official = {
    '20250102': {'contract_code_kis': '175W01','official_volume': '1','expiry_date':'2025-01-20'},
    '20250103': {'contract_code_kis': '175W01','official_volume': '1','expiry_date':'2025-01-20'},
    '20250106': {'contract_code_kis': '175W01','official_volume': '1','expiry_date':'2025-01-20'},
    '20250107': {'contract_code_kis': '175W01','official_volume': '1','expiry_date':'2025-01-20'},
    '20250108': {'contract_code_kis': '175W01','official_volume': '1','expiry_date':'2025-01-20'},
    '20250109': {'contract_code_kis': '175W01','official_volume': '1','expiry_date':'2025-01-20'},
    '20250110': {'contract_code_kis': '175W01','official_volume': '1','expiry_date':'2025-01-20'},
    '20250113': {'contract_code_kis': '175W01','official_volume': '1','expiry_date':'2025-01-20'},
    '20250120': {'contract_code_kis': '175W01','official_volume': '1','expiry_date':'2025-01-20'},
    '20250121': {'contract_code_kis': '175W02','official_volume': '1','expiry_date':'2025-02-17'},
}
ranks = {d:i for i,d in enumerate(sorted(official))}

def t(a,b,limit=1,allowed=True,kind=None):
    x=classify_boundary(q(a),q(b),official,ranks,limit)
    assert x.allowed == allowed, (a,b,x)
    if kind: assert x.kind==kind,(a,b,x)
    return x

if __name__=='__main__':
    assert t('2025-01-10T09:01','2025-01-10T09:03',0,False).missing_minutes==1
    assert t('2025-01-10T09:01','2025-01-10T09:03',1,True,'INTRADAY_SMALL_GAP').missing_minutes==1
    assert t('2025-01-10T09:01','2025-01-10T09:04',1,False).missing_minutes==2
    assert t('2025-01-10T09:01','2025-01-10T09:04',2,True).missing_minutes==2
    t('2025-01-10T09:01','2025-01-10T09:05',2,False,'INTRADAY_LARGE_GAP')
    t('2025-01-03T15:30','2025-01-06T09:00',0,True,'NORMAL_CLOSED_SESSION')
    t('2025-01-06T15:30','2025-01-07T09:01',0,False,'LOGGER_WINDOW_EDGE_MISSING')
    t('2025-01-06T15:30','2025-01-07T09:01',1,True,'SESSION_EDGE_SMALL_GAP')
    t('2025-01-06T15:29','2025-01-07T09:01',1,True,'SESSION_EDGE_SMALL_GAP')
    t('2025-01-06T15:28','2025-01-07T09:02',2,True,'SESSION_EDGE_SMALL_GAP')
    t('2025-01-06T15:27','2025-01-07T09:02',2,False,'LOGGER_WINDOW_EDGE_MISSING')
    t('2025-01-06T15:30','2025-01-09T09:00',2,False,'MISSING_OFFICIAL_TRADING_DATES')
    x=classify_boundary(q('2025-01-20T11:30'),q('2025-01-21T09:00','175W02'),official,ranks,2)
    assert not x.allowed and x.kind=='REF_CHANGE_UNVERIFIED_ROLL'
    t('2025-01-10T09:01','2025-01-10T09:02',0,True,'CONTIGUOUS')
    print('TEST_GAP_POLICY_PASS: 14 boundary tests; zero synthetic market prices')
