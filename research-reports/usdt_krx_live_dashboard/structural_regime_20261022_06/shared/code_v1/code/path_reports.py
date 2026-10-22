# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Pure reporting: do not change numerical accounting.
from __future__ import annotations
import json
from collections import defaultdict
from runner import table

LABELS={"driver":"가격주도 원인 선별","residual":"이동 중심 이탈·복귀","momentum":"괴리 확대 추세",
        "trail":"비용차감 이익 추적","opportunity":"반전·기회 전환","selector":"성숙 과거 예측 선택"}
COMMON="""
운용: 17계약+170000USDT 한묶음, 추가진입/양방향 동시/부분청산 없음. 선물초기현금3천만원에서 손익 누적, 외부입금/계좌간 이체 없음. 부족한17계약은 전량거절. 현물은 충분조달 가정이며 조달필요액/평균노출 별도. 현물편도0.05%, 선물편도600원/계약+0.0003157%, 각레그편도2bp 및 롤 양쪽 비용 유지. 역배차입과 비용 미검증. 다음 연속 관측1분 OPEN 대용체결이며 실제17계약 호가체결 검증은 아님.

신호: 당일까지 관측된 종가만 사용, 과거 center/std는 현재봉 제외. 월물교체 또는30분 초과 공백에서는 준비기간 재시작. 무거래/공백 보간 없음. 이동 중심 전략은 기존 고정0 기준 보정과 달리 중심의 양쪽을 별도 상태로 인식하므로 양수괴리에서도 정배가 가능. 추세형은 괴리 확대 방향으로 헤지 방향을 뒤집으며 수량은 동일. 추적청산은 완료비용까지 포함한 관측 순수익률의 과거 최고 대비 하락을 사용하며 미래 극값은 사용하지 않음.

과거성적 선택기는 과거에 이미 끝난 일정 관측기간의 가상 예측손익만 사용하고 정해진 관측간격마다 선택한다. 이 겹치는 probe는 투자 가능한 별도 계좌수익이 아니며 학습용 예측지표다. 그때 선택된 신호만 실제 단일 PAPER 계좌에 전달한다. 미래 월 최고전략을 소급선택하지 않음. 선택상태 변경 시 보유중 전량청산 판단에도 현시점 선택 정책을 적용하며 추가진입하지 않음.

기존 B 및 대기형과 원본/완료결과는 보존. 동일 승인 탐색기간이며 독립 OOS 아님. Final OOS/Gateway/예약/수집기 접근변경 없음. 7월6일~8월2일 증거금 일정 추론 한계 유지. INPUT_NOT_REMOTELY_REPRODUCIBLE: 원시 시장 입력은 D: 해시참조.
"""

def write_prereg_report(name, out) -> None:
    r=json.loads((out/"settings.json").read_text())
    report=f"# 구조적 신규 가설 {name} 사전등록\n\n"
    report+=f"새로운 상태판단/진입/청산 구조50조건, 미세조정0조건. 배분: {r['allocation']}. 실행 전 입력·조건·코드 해시 고정.\n\n"
    report+="큰 개선 목표: 점수25% 이상·실현순이익6천만원 이상·완료42회 이상·MDD935만원 이하·잔여0·초기/유지/롤부족 및 진입거절0 모두 충족. 허용차1e-8%p/0.01원. 승률100%는 요구하지 않음.\n\n"
    report+="주 점수는 각 완료사이클의 비용차감순손익/최초현물진입명목절대값×100 단순합. 잔여손익 분리. 정확한 조건·가설의 개선의도는settings.json. 1~5배치는 여섯 구조를 고르게,6~10은 먼저 완료한 결과를 토대로 구조별 유망 규칙의 새 조합과 넓은 후보를 절반씩 생성. 이미 계산한 결과 재실행 없음.\n"+COMMON
    (out/"REPORT_KO.md").write_text(report,encoding="utf8")

def write_result_report(number,out,rows,allrows,rules,summary) -> None:
    groups=defaultdict(list)
    for r in allrows:groups[r["execution_path_sha256"]].append(r["candidate_id"])
    table(out/"equivalent_execution_paths.csv",[dict(sha256=k,count=len(v),candidate_ids=";".join(v)) for k,v in groups.items()])
    table(out/"exit_trigger_counts.csv",[{k:r[k] for k in r if k.startswith("exit_") or k in ("candidate_id","structure")} for r in rows])
    risk=[r for r in allrows if r["cycles"] and r["margin_shortage_free"] and (r["mdd_krw"]<9349999.99 or r["longest_hold_minutes"]<41887)]
    table(out/"risk_reduction_candidates.csv",sorted(risk,key=lambda x:x["score_pct"],reverse=True))
    report=f"# 구조적 신규 가설 {number}배치 결과\n\n"
    report+=f"이번50·누적{number*50}/500조건. 큰 개선 목표 통과 이번{summary['batch_qualified_count']}개 / 누적{summary['qualified_count']}개. 동일 체결/계좌경로{len(groups)}개.\n\n"
    report+="|후보|구조|완료|승률%|점수%|실현순이익 원|PF|MDD 원|잔여|\n|---|---|---:|---:|---:|---:|---|---:|---:|\n"
    for r in sorted([x for x in rows if x["cycles"]],key=lambda x:x["score_pct"],reverse=True)[:5]:
        pf=r["profit_factor_krw"] if r["profit_factor_krw"] is not None else r["profit_factor_status"]
        report+=f"|{r['candidate_id']}|{LABELS[r['structure']]}|{r['cycles']}|{r['win_rate_pct']:.4f}|{r['score_pct']:+.10f}|{r['net_realized']:,.2f}|{pf}|{r['mdd_krw']:,.2f}|{r['residual_contracts']}|\n"
    r=summary["selected"]
    if r:
        report+="\n이번 선정의 정확한 조건:\n"+json.dumps(rules[r["candidate_id"]],ensure_ascii=False,indent=2)+"\n"
        report+=f"\n기준 B와 같은 완료구간{r['same_B_intervals']}개, 다른구간{r['changed_completed_intervals']}개. 최대평가손실{r['maximum_open_loss_krw']:,.2f}원, 평균/최장보유{r['average_hold_minutes']/1440:.5f}/{r['longest_hold_minutes']/1440:.5f}일. 최소 초기/유지증거금여유{r['minimum_initial_headroom_krw']:,.2f}/{r['minimum_maintenance_headroom_krw']:,.2f}원.\n"
        report+=f"\n초기부족평가{r['initial_margin_deficit_marks']}회, 유지부족평가{r['maintenance_breach_marks']}회, 롤부족{r['insufficient_rolls']}회, 진입거절{r['admission_rejections']}건. 잔여 청산비용차감{r['residual_net_after_exit_cost']:,.2f}원, 종료가정점수{r['forced_terminal_score_pct']:+.10f}%. 평균 관측 현물노출{r['average_spot_exposure_krw']:,.2f}원, 조달필요{r['spot_financing_proxy_krw']:,.2f}원.\n"
    report+="\n기준B:42회·16.7054302006977%·41,295,918.91원·MDD935만원·잔여0. 60분대기형:42회·16.8127937696%·41,567,722.36원. 큰 개선은모든 목표 동시충족일 때만 표시. 미달사유와0거래·미청산·운용부적격도보존. 수익률과원화순손익순위를혼동하지않음.\n"+COMMON
    (out/"REPORT_KO.md").write_text(report,encoding="utf8")
