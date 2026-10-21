from __future__ import annotations

import gzip
import json
import shutil

from package import manifest
from runner import ROOT, SOURCE_HASH, MARGIN_HASH, table, write_json


def main():
    out=ROOT/'publish_payloads/repair_v2'
    assert not out.exists();out.mkdir(parents=True)
    shutil.copytree(ROOT/'code',out/'code',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT/'unit_tests_v2.json',out/'unit_tests.json')
    shutil.copy2(ROOT/'control_reproduction/reference_regression.json',out/'reference_regression.json')
    shutil.copy2(ROOT/'preregistration/batch_0001.json',out/'settings.json')
    table(out/'results.csv',[json.loads((ROOT/'control_reproduction/result.json').read_text())])
    with gzip.open(ROOT/'control_reproduction/fills.csv.gz','rt',encoding='utf8',newline='') as f:
        import csv
        table(out/'control_fills.csv',list(csv.DictReader(f)))
    table(out/'costs.csv',[dict(spot_fee=.0005,futures_fee_per_contract=600,clearing=.000003157,slippage_bp_per_leg_per_side=2,rollover='both sides',borrow='UNVERIFIED_NOT_INCLUDED')])
    write_json(out/'environment.json',dict(python='3.12.0',numpy='2.2.6',numba='0.61.2',storage='D_ONLY',execution='PAPER_EXPLORATORY_ONLY'))
    write_json(out/'provenance.json',dict(input_sha256=SOURCE_HASH,margin_sha256=MARGIN_HASH,source_status='INPUT_NOT_REMOTELY_REPRODUCIBLE',previous_commit='54b0d97ed8464b5e05f11bd0a5220c97547e8c0c',
        original_first_grid_sha256='730e03f33bf17738ad7c48ca31e421ca6dd6cb6f1551bb36960b0a3a991750b5',control_recomputed=False,first_grid_changed=False,engine_or_signal_changed=False))
    (out/'REPORT_KO.md').write_text('''# 검산기 정산 명칭 수정 및 재개 전 검증

검산기의 이벤트 코드 5는 실제 체결 원장에 맞춰 SETTLE로 연결합니다. 계좌 평가 단계 SETTLEMENT는 별도의 대응표로 유지합니다. 가격·신호·수량·현금·비용 엔진은 변경하지 않았습니다.

17개 합성 회귀 검사를 통과했습니다. 정산·롤오버 청산·롤오버 신규진입을 각각 삭제했을 때 대조 검사가 실패하는 검사도 포함합니다. 실제 기준 원장의 진입45, 청산45, 정산98, 롤오버 청산5·신규진입5를 모두 대조했습니다.

저장된 CONTROL을 재계산하지 않고 다시 검증했습니다. 45사이클, 수익률 합계 +13.15221660791525%, 순이익 32,356,627.76736317원, MDD 9,350,000원입니다. 369,010개 계좌 평가 기록의 최대 차이는 0.000000521541원으로 허용차 0.01원 이내입니다. 정산·롤오버·매매 비용/손익 차이는 0.000000000466원 이하입니다.

첫 50조건의 등록 해시는 그대로입니다. 이 커밋은 수정 코드·회귀 검증 사전 게시이며 신규 스윕 완료가 아닙니다. 최초17계약·170,000 USDT, 선물초기3,000만원, 추가진입 금지, 양방향 한 묶음, 기존2bp비용을 유지합니다. 역배 차입은 미검증 이론값입니다. Final OOS와 Gateway·예약 작업은 접근·변경하지 않았습니다.
''',encoding='utf8')
    manifest(out);print(str(out),flush=True)


if __name__=='__main__':main()
