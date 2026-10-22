# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: python -B code/bootstrap.py package_audit.py after audits.
from __future__ import annotations
import datetime as dt,json,platform,shutil,sys
from audit_common import ROOT,PUBLIC,LOCAL,sha,read_csv,table,save

def main()->None:
    summary=json.loads((PUBLIC/'summary.json').read_text(encoding='utf8'))
    validation=json.loads((PUBLIC/'validation.json').read_text(encoding='utf8'))
    source=json.loads((ROOT/'metadata/frozen_scope.json').read_text(encoding='utf8'))
    rows=read_csv(PUBLIC/'results.csv')
    assert validation['downloaded_files']==626 and validation['independent_file_parse_checks']==626
    assert summary['sensitive_pattern_hits']==0
    assert summary['unparsed_price_lines']==0 and summary['filename_date_mismatch_blocks']==0
    local_hashes=[]
    for directory in (ROOT/'raw',LOCAL):
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                local_hashes.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=sha(path.read_bytes()),disposition='D_ONLY_NOT_REDISTRIBUTED'))
    table(PUBLIC/'local_artifact_hashes.csv',local_hashes)
    code_dest=PUBLIC/'code';code_dest.mkdir(exist_ok=True)
    for path in (ROOT/'code').iterdir():
        if path.suffix in ('.py','.mjs'):shutil.copyfile(path,code_dest/path.name)
    save(PUBLIC/'settings.json',source)
    save(PUBLIC/'environment.json',dict(python=sys.version,executable=sys.executable,platform=platform.platform(),network_runtime='Node v26.7.0 built-in HTTPS fetch',dependencies='Python standard library only',working_directory=str(ROOT),all_generated_files_on_D=True,system_environment_modified=False))
    tree_check=json.loads((ROOT/'metadata/commit_tree_verification.json').read_text())
    assert tree_check['inventory_matches'] and tree_check['truncated'] is False
    save(PUBLIC/'provenance.json',dict(source=source['source_repository'],commit=source['source_commit'],tree=source['source_tree'],full_tree_entries=1167,truncated=False,commit_tree_crosscheck=tree_check,original_files=626,original_bytes=85340708,original_integrity='Each file checked against tree size, Git blob SHA-1 and SHA-256',README_current_http=404,license_current_http=404,historical_readme_deletion_commit='1975339655beecf97bbe26fecb481779e276c3ec',historical_readme_source_commit='1d535def97d1b6762e9240e1e00c36b9c766f4c7',historical_readme_sha256=sha((ROOT/'metadata/historical_README.local.md').read_bytes()),historical_readme_conclusion='No product, timezone, exchange, quote mapping or license explanation',generator_code_found=False,raw_data_publication='WITHHELD_REPUBLICATION_PERMISSION_NOT_ESTABLISHED',raw_access='D_ONLY_LOCAL; originals can be fetched separately from the pinned upstream repository while available',raw_fully_archived_in_our_github=False,protected_oos_content_opened=False,reference_comparisons='Q4-2025 only, conditional same-clock labels; no series merging'))
    save(PUBLIC/'checkpoint.json',dict(status='LOCAL_AUDIT_COMPLETE_PENDING_REMOTE_VERIFICATION',months_completed=12,files_downloaded=626,backtest_started=False,failed_downloads=0,source_commit=source['source_commit']))
    table(PUBLIC/'fills.csv',[],['status','reason_no_fills'])
    table(PUBLIC/'costs.csv',[dict(status='NOT_APPLICABLE',reason='DATA_AUDIT_ONLY_NO_STRATEGY_OR_ORDER_EXECUTION')])
    monthly_table='|월|대상/다운로드|선물/현물환 파일|가격일|네 가격 관측|선물 오류 줄|관련 현물환 오류 줄|최초~마지막 가격 기록|판정|\n|---|---:|---:|---:|---:|---:|---:|---|---|\n'
    for r in rows:
        monthly_table+=f"|{r['month']}|{r['target_files']}/{r['downloaded_files']}|{r['future_files']}/{r['related_spot_files']}|{r['future_price_days']}|{int(r['complete_pair_observations']):,}|{r['future_error_lines']}|{r['related_spot_error_lines']}|{r['first_price']} ~ {r['last_price']}|출처·월물·시간 미확인|\n"
    report=f'''# 2025년 공개 가격 로그 수집·품질 감사

1. 원본 626개를 모두 받았지만 공식 1분봉 확보를 뜻하지 않습니다.
2. 선물 로그 261개 중 241일에 가격이 있고, 네 가격이 모두 있는 관측은 101,333개입니다.
3. 1~9월에도 가격값은 있습니다: 175일, 네 가격 관측 68,233개입니다.
4. 그러나 거래소·미국달러선물 상품·월물·시간대·매수/매도 호가 의미가 확인되지 않았습니다.
5. 5월20일~6월16일의 20개 선물 파일에는 가격이 없고 오류만 있습니다.
6. 기존 KRX 분봉을 대체하거나 B의 2025년 전체 검증 입력으로 승인할 수 없습니다.
7. B 실행·스윕·수익률 계산·주문은 하지 않았고, 제3자 원문은 D:에만 보존했습니다.

{monthly_table}

## 수치의 정의
가격일·관측은 future_result 파일만 집계합니다. 네 가격 관측은 같은 기록시각 블록에 USDT 매수가·매도가와 선물 매수가·매도가가 모두 양수인 경우입니다. 시세 발생시각의 동시성을 인증한 수치가 아닙니다. 관련 spot_result 파일의 USD(원화)는 별도 현물환으로 취급해 선물 가격으로 사용하지 않았습니다. 두 파일 종류의 관측을 합치지 않았습니다. 파일 수에는 관련 현물환 파일도 포함했습니다. 오류는 메시지 줄 수이며 한 줄은 우선순위에 따라 한 분류에만 집계했습니다. 토큰 만료 상태 안내도 오류 유형에 포함합니다. 양수값의 존재를 상품·가격 의미까지 검증된 것으로 부르지 않습니다.

## A: 다운로드 가능한 범위
고정 저장소 [kimp741/data](https://github.com/kimp741/data/tree/{source['source_commit']})의 main 커밋은 {source['source_commit']}입니다. 커밋의 실제 tree는 {source['source_tree']}입니다. 재귀 트리 1,167개 항목, truncated=false를 확인하고 커밋의 tree ID로 다시 읽은 목록과 교차 대조했습니다. 2025년 future_result 261개와 spot_result 365개 총626개, 85,340,708바이트를 모두 다운로드했습니다. 1월부터12월까지 순차로 내려받았고 Git blob SHA-1·바이트·SHA-256을 확인했습니다. 같은 해시 사본은 재사용하며 실패 재시도는 최대3회입니다. 실패 파일은0개입니다. 없는 날짜는 missing_files.csv(선물104일)에 별도로 기록했습니다. 파일 부재는 휴일 또는 미수집을 구분하기 전까지 시장 데이터 누락으로 단정하지 않습니다.

## B: 실제 가격이 있는 범위
전체 선물 로그의 가격값 범위는 2025-01-01 09:00~2025-12-31 23:58의 원문 시각 라벨입니다. 월별 정확한 첫·끝은 위 표, 날짜별 첫·끝은 date_time_coverage.csv, 시간별 개수는 hourly_clock_coverage.csv, 연속 관측·내부 공백은 continuous_segments.csv와 observation_gaps.csv를 참조합니다. 첫·끝 사이가 모두 확보됐다는 뜻은 아닙니다. 1~11월은 주로09:00~15:30 기록입니다. 12월17일21:39 이후로 보이는 야간 시각 기록이 추가되고12월18일 이후 일부 날짜는00:00~05:59 및18:00~23:58 라벨도 있습니다. 야간 시각 라벨의 네 가격 관측은7,330개지만 KRX 야간 거래일로 귀속한 수치는 아닙니다. 원문 시간대와 실제 시세시각이 미확인이라 확정 야간 데이터로 인정하지 않았습니다.

5월20~30일의9개 파일과6월2~16일의11개 파일(일부 휴일 포함)은 가격 없이 오류만 있습니다. 구체적인 날짜20개는 error_only_future_dates.csv를 참조하십시오. 첫 회복 가격은6월17일09:04입니다. 호가 없음 메시지가 주원인이지만 월물 교체 실패가 원인이라는 추측은 확정하지 않았습니다. 소스 생성 코드가 없어 원인을 입증할 수 없습니다.

## C: B 검증에 사용할 수 있는 범위
현재 상품·월물·거래소·시간대를 모두 검증해 B 입력으로 승인 가능한 기간은 없습니다. 모든 월의 판정은 '가격은 있으나 출처/월물/시간 미확인'입니다. raw_label과 원문 퍼센트는 D:의 정규화 JSONL에 별도 보존했고 bid/ask 및 B 괴리율로 확정하거나 재계산하지 않았습니다. futs_askp1/futs_bidp1 및 KIS 형식 오류 메시지는 단서지만 미국달러선물 특정 계약을 입증하지 못합니다. 가격 유사성으로 업비트나 특정 월물을 지정하지 않았습니다.

## 누락·오류·품질
부분 가격 관측63개, 중복 시각 블록5개, 동일 시각 상충 가격1개, 0이하 가격 필드123개가 있습니다. 값과 중복을 삭제·수정하지 않았습니다. 모든 값의 원본 파일·출처 SHA·줄 번호·기록시각을 유지합니다. 30분 이상 같은 가격 묶음이 반복된 파일299개를 의심 대상으로 표시했으며 현물환 파일도 포함합니다. 같은 가격이라는 이유만으로 오류로 삭제하지 않았습니다. 파일 날짜 불일치 블록0개, 인식하지 못한 가격 형식 줄0개입니다. 오류 분류 전체는 validation.json과 error_classification.csv를 참조하십시오. 민감정보 패턴 검사는 원문에서0건이었고 공개 대상도 별도 검사합니다. 패턴 검사가 비밀정보 부재를 절대 보장한다고 주장하지 않습니다.

기록시각을 가정상 KST로 놓으면 가격이 있는17개 날짜는 기존 공식 정규장 거래일 표에 없습니다. 예를 들어1월1일·12월25일에도 가격 기록이 있습니다. 이는 실거래 가격이라는 주장을 강화하지 않으며 시세 정체·출처·시간대 확인이 필요합니다. calendar_session_checks.csv의 계약코드는 비교용 기존 자료의 월물일 뿐 제3자 로그에서 검증한 월물이 아닙니다. 원문에는 계약코드·만기·월물교체 규칙이 없습니다.

공식 KRX 안내는 자체 야간시장과 종전 연계시장을 구분합니다. [KRX 야간시장 안내](https://global.krx.co.kr/contents/GLB/02/0201/0201041004/GLB0201041004.jsp), [2025 안내 팜플릿](https://global.krx.co.kr/contents/GLB/02/0201/0201041003/KRX%20Derivatives%20Market%20Night%20Session%20Phamplet.pdf)을 출처로 남깁니다. 일부 웹 본문은403·타임아웃이라 당시 전체 특수일 일정을 새로 인증하지 않았습니다. 2025년6월 이전 Eurex 연계를 이후 KRX 자체 야간시장과 같은 자료로 연결하지 않았습니다. 시간대 미확인 로그에 현재 시간표를 적용해 완전성을 판정하지 않았고, 과거 존재하지 않은 야간 세션도 누락으로 세지 않았습니다.

## 기존 Q4 자료와 교차 대조
D:의 KRX23,149개 분봉과10~12월 업비트 분봉을 읽기 전용으로 참조했습니다. 원본 경로·SHA-256은 reference_input_hashes.csv에 있습니다. 원문 시간대를 KST라고 임시 가정한 동일 라벨 비교일 뿐, 기록시각과 시세시각 일치를 검증하지 않았습니다. 비교군24개, 가격 필드별 비교220,936개이며 고유 동시 관측 수와 다릅니다. 각 원문 매수/매도 라벨을 유지해 분봉 시가·종가와의 차이 분포를 cross_comparison_distribution.csv에 기록했습니다. 호가와 OHLCV의 관측 유형이 다르므로 차이가0이 아니라고 오류로 판정하지 않았습니다. 일부 유사한 가격이나 작은 차이도 상품·월물·거래소의 정확성 인증으로 쓰지 않았습니다. 동일 시각의 동일 유형 과거 호가 원본으로 대조한 것은 아닙니다. 개별 대조행은 D:에만 보존했습니다. 두 자료를 하나의 시계열로 합치지 않았습니다.

## 2025년 전체 검증을 막는 항목과 다음에 필요한 증거
- 당시 생성 코드와 버전: 테더 거래소, 실제 KRX 상품·계약코드, 매수/매도 라벨의 bid/ask 의미.
- 기록 시간대·시세 발생시각·두 API 요청 간 시간차와 지연 처리.
- 20개 오류 전용 날짜, 나머지 내부 공백, 실제 무거래와 API 실패 구분.
- 월물·만기·롤오버, 공식 거래일·당시 거래시간·정산 및 증거금 일정.
- 17계약·170,000 USDT의 전량 체결을 검증할 호가 잔량과 차입 자료.
- 자료 이용·재배포 허용 조건. 현재 README와 LICENSE는404입니다. README 삭제 이력1건을 제한적으로 확인해 삭제 전 문서를 읽었지만 내용은 자료 의미·허가를 설명하지 않았습니다. 현재 공개 코드가 없고 같은 소유자의 공개 저장소 목록에서도 생성 코드를 찾지 못했습니다. 과거 모든 버전에 생성 코드가 없었다고 단정하지 않습니다.

따라서 1~9월에도 가격값은 존재하지만, 기존 KRX 공식 1분봉을 대체하지 못합니다. 출처·시간·월물 미확인인 별도 가격/호가 로그 참고자료입니다. 누락을 앞값·일봉·보간으로 채우거나 가격을 OHLC로 복제하지 않았습니다. B 성과를 계산하지 않았습니다.

## 재현·보관
원본·정규화·개별 차이행은 {ROOT} 아래 raw/와 derived_local/에만 보존합니다. 제3자 원문과 전체 정규화 파일은 허가가 확인되지 않아 우리 공개 GitHub에 복제하지 않습니다. source_files.csv는 원본 바이트·Git blob SHA·SHA-256, local_artifact_hashes.csv는 로컬 산출물 해시를 제공합니다. 공개 패키지에는 우리 감사 코드와 집계·검증 결과만 포함합니다. 전체 원문 재현은 고정 upstream이나 D: 사본에 의존합니다.

기존 B·시장 원본·Final OOS·Gateway·OpenClaw·예약 작업·수집기는 변경하지 않았습니다. KIS API·인증파일·토큰도 사용하지 않았습니다. GitHub 게시 후 새 원격 읽기로 공개 manifest의 각 파일 바이트·SHA-256을 검증합니다. 게시 검증 영수증은 로컬 publication/에 따로 남깁니다.
'''
    (PUBLIC/'REPORT_KO.md').write_text(report,encoding='utf8')
    (PUBLIC/'README_REPRODUCE_KO.md').write_text('재현 순서: Node로 code/download.mjs 실행 → Python으로 code/bootstrap.py audit_logs.py → compare_existing.py → additional_quality.py → package_audit.py. 원본 tree 메타데이터는 provenance의 고정 커밋에서 GitHub 공식 git/trees API로 저장한다. frozen_scope.json 설정과 기존2025년 비교 입력을 D:에 준비한다. 필요한 기존 참조 자료는 reference_input_hashes.csv와 정확한 SHA로 확인한다. 다운로드 시 기존 blob·크기 일치 파일은 재사용하며 원문을 덮어쓰지 않는다. 파서는 own derived_local만 다시 생성할 수 있다. code 디렉터리를 별도 D: root에 두고 metadata·raw·출력도 같은 root에 둔다. 공개 원문을 실행하지 않는다. 일부 입력은 재배포 권한 미확인으로 D:에만 있어 이 패키지 단독의 완전한 원문 재현을 보장하지 않는다. 전략 실행 코드는 포함하지 않았으며 모든 분석은 가격 로그 품질 감사이다.\n',encoding='utf8')
    print(json.dumps(dict(local_payload=str(PUBLIC),public_files=sum(p.is_file() for p in PUBLIC.rglob('*')),local_only_artifacts=len(local_hashes),local_only_bytes=sum(r['bytes'] for r in local_hashes))))

if __name__=='__main__':main()
