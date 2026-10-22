# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Reporting only; frozen market input and costs are not altered.
from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict
from runner import ROOT,table
LABELS={1:'방향별 진입·회복 분리',2:'동일 진입의 청산 효과 비교',3:'확인 진입·재진입 대기',4:'과거 시장상태 적응',5:'장기 보유·손실 위험 감소'}

def write_prereg_report(name: str, out: Path) -> None:
    registration=json.loads((out/'settings.json').read_text())
    category=registration['conditions'][0]['category']
    report=f'# B 파생 가설 사전등록 {name}\n\n{LABELS[category]} 신규50조건입니다.\n\n'
    report+='전체500조건·10배치 순서와 코드/입력 SHA는 신규 매매 전 고정했습니다. 기존 모든 연구 조건표의 메타데이터를 읽고 동일 규칙은 제외·재사용 참조로 분류했습니다. 기준 BF-09-027의 순손익 익절은0.7% 그대로이며 파생 후보의 정확한 변경은 settings.json에 있습니다.\n\n'
    report+='선물17계약·현물170,000 USDT 한묶음, 추가진입 없음, 선물초기현금3천만원, 외부입금·계좌자동이체 없음. 현물 충분조달 가정의 필요액은 별도 기록합니다. 증거금 부족이면17계약 전량거절입니다. 다음 연속관측1분 시가 대용 체결, 현물편도0.05%, 선물600원/계약+청산율0.0003157%, 각레그편도2bp·롤양쪽 비용을 유지합니다.\n\n'
    report+='우선 목표는 기준16.7054302006977%보다1e-8%p 초과, 완료42회 이상·잔여0·MDD935만원 이하(0.01원 허용)·초기/유지/롤 자금부족 및 진입거절0입니다. 승률100%는 합격요건이 아닙니다.\n\n'
    report+='시장상태는 이전N개 관측만 사용하고 월물 교체 또는30분 초과 공백에서 재설정합니다. 신호봉 제외, 완전 준비기간 전 진입 없음, 결측 보간 없음. 대기 중 신호를 큐에 보관하지 않고 새로운 통과만 허용합니다. 확인 진입의 기준은 실제 확인 신호봉입니다.\n\n'
    report+='동일 탐색자료를 본 후 제안한 후속 가설이며 독립 OOS 검증이 아닙니다. 역배 차입·비용과 과거호가17계약 체결 미검증, 7월6일~8월2일 증거금 일정 추론 한계를 유지합니다. 원시는 D:에만 보존하고 INPUT_NOT_REMOTELY_REPRODUCIBLE입니다. 보호Final OOS·기존 결과·Gateway·예약작업·수집기는 변경하지 않습니다.\n'
    (out/'REPORT_KO.md').write_text(report,encoding='utf8')

def write_result_report(number, out, rows, allrows, rules, summary) -> None:
    """Report actual path changes and trigger overlap, plus risk-only candidates."""
    category=(number-1)//2+1
    fields=('candidate_id','exit_gap_only','exit_profit_only','exit_gap_profit_both','exit_other','exit_gap_any','exit_profit_any','exit_loss_stop','exit_time','exit_stall','execution_path_sha256','top3_positive_return_share_pct','top5_positive_return_share_pct')
    table(out/'exit_trigger_counts.csv',[{k:r[k] for k in fields} for r in rows])
    groups=defaultdict(list)
    for r in allrows:groups[r['execution_path_sha256']].append(r['candidate_id'])
    table(out/'equivalent_execution_paths.csv',[dict(execution_path_sha256=k,conditions=len(v),candidate_ids=';'.join(v)) for k,v in groups.items()])
    risk=[r for r in allrows if r['cycles'] and r['margin_shortage_free'] and (r['mdd_krw']<9350000-.01 or r['longest_hold_minutes']<41887)]
    table(out/'risk_reduction_candidates.csv',sorted(risk,key=lambda r:r['score_pct'],reverse=True))
    report=f'# B 파생 가설 {number}배치 — {LABELS[category]}\n\n'
    report+=f'이번50조건, 누적{number*50}/500조건을 계산·독립 원장 검산했습니다. 목표 충족 이번 {summary["batch_qualified_count"]}개 / 누적 {summary["qualified_count"]}개입니다.\n\n'
    report+='주 점수는 완료사이클별 비용차감 순손익/최초 현물 진입명목 절대값×100의 반올림 전 단순합계입니다. 미청산은 분리하고 종료가정청산 점수도 기록합니다. 새 기록 허용차는1e-8%p입니다. 동일 경로는 별도 묶었으며 독립 표본으로 세지 않습니다.\n\n'
    report+='|후보|완료|승률%|수익률합계%|실현 순이익 원|PF|MDD 원|잔여|\n|---|---:|---:|---:|---:|---|---:|---:|\n'
    selected=sorted([r for r in rows if r['cycles']],key=lambda r:r['score_pct'],reverse=True)[:5]
    for r in selected:
        pf=f'{r["profit_factor_krw"]:.4f}' if r['profit_factor_krw'] is not None else r['profit_factor_status']
        report+=f'|{r["candidate_id"]}|{r["cycles"]}|{r["win_rate_pct"]:.4f}|{r["score_pct"]:+.10f}|{r["net_realized"]:,.2f}|{pf}|{r["mdd_krw"]:,.2f}|{r["residual_contracts"]}|\n'
    r=summary['selected']
    if r:
        report+='\n선정 후보의 정확한 규칙:\n'+json.dumps(rules[r['candidate_id']],ensure_ascii=False,indent=2)+'\n'
        report+=f'\n최대평가손실 {r["maximum_open_loss_krw"]:,.2f}원, 평균/최장보유 {r["average_hold_minutes"]/1440:.5f}/{r["longest_hold_minutes"]/1440:.5f}일, 최소초기/유지증거금여유 {r["minimum_initial_headroom_krw"]:,.2f}/{r["minimum_maintenance_headroom_krw"]:,.2f}원입니다.\n'
        report+=f'회복단독 {r["exit_gap_only"]}회·익절단독 {r["exit_profit_only"]}회·동시 {r["exit_gap_profit_both"]}회·그외 {r["exit_other"]}회이며 개별근거 exit_attribution.csv를 전체원장 TAR에 포함했습니다. 잔여 청산비용차감 평가손익 {r["residual_net_after_exit_cost"]:,.2f}원, 종료가정청산 점수 {r["forced_terminal_score_pct"]:+.10f}%입니다.\n'
    report+='\n기준 BF-09-027의42회·16.7054302006977%·41,295,918.91원·MDD935만원·잔여0과 비교합니다. 기준 익절0.7%는 변경하지 않았습니다. 모든 규칙과 코드 해시는 실행 전에 등록했습니다. PF는 비용차감 완료사이클 원화 이익합/손실합 절대값이며 손실0이면 별도상태입니다.\n\n'
    report+='17계약·170000USDT·한방향 한묶음·추가진입/외부입금/자동이체 없음, 기존 수수료·각레그편도2bp·롤오버 양쪽 비용을 유지합니다. 현물 충분조달, 역배 차입/비용 미검증, 다음 연속 관측분 시가 체결대용값, 분중손실/과거호가 부재, 증거금 일정 추론 한계가 있습니다. 미달 후보와 위험감소 후보를 모두 보존합니다. 탐색자료 내 결과이며 보호Final OOS·Gateway·OpenClaw·예약작업·수집기는 변경하지 않았습니다.\n'
    (out/'REPORT_KO.md').write_text(report,encoding='utf8')
