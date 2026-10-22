# B 파생 가설 8배치 — 과거 시장상태 적응

이번50조건, 누적400/500조건을 계산·독립 원장 검산했습니다. 목표 충족 이번 0개 / 누적 1개입니다.

주 점수는 완료사이클별 비용차감 순손익/최초 현물 진입명목 절대값×100의 반올림 전 단순합계입니다. 미청산은 분리하고 종료가정청산 점수도 기록합니다. 새 기록 허용차는1e-8%p입니다. 동일 경로는 별도 묶었으며 독립 표본으로 세지 않습니다.

|후보|완료|승률%|수익률합계%|실현 순이익 원|PF|MDD 원|잔여|
|---|---:|---:|---:|---:|---|---:|---:|
|BP-08-049|39|100.0000|+14.3776546588|35,751,780.86|INFINITE_NO_LOSSES|10,387,000.00|17|
|BP-08-001|38|100.0000|+14.2319404402|35,142,880.33|INFINITE_NO_LOSSES|8,126,000.00|17|
|BP-08-047|29|100.0000|+12.5471579114|30,928,548.24|INFINITE_NO_LOSSES|8,126,000.00|0|
|BP-08-013|32|100.0000|+12.4332555291|31,048,154.21|INFINITE_NO_LOSSES|8,007,000.00|17|
|BP-08-048|29|100.0000|+12.2648938218|30,233,104.03|INFINITE_NO_LOSSES|8,126,000.00|0|

선정 후보의 정확한 규칙:
{
  "family": "relative",
  "long_entry_gap_pct": -0.97,
  "short_entry_gap_pct": 0.85,
  "long_recovery_pp": 0.6,
  "short_recovery_pp": 0.6,
  "long_absolute_exit_gap_pct": null,
  "short_absolute_exit_gap_pct": null,
  "confirmation_pp": 0,
  "confirmation_expiry_calendar_minutes": null,
  "max_hold_minutes": null,
  "gap_stop_pp": null,
  "pnl_stop_pct": null,
  "pnl_profit_pct": 0.7,
  "threshold_mode": "volatility",
  "window_observations": 180,
  "center_weight": 0.35,
  "volatility_entry_scale": true,
  "volatility_recovery_scale": false
}

최대평가손실 9,491,257.26원, 평균/최장보유 5.81998/39.34861일, 최소초기/유지증거금여유 10,147,787.45/14,673,215.50원입니다.
회복단독 39회·익절단독 0회·동시 0회·그외 0회이며 개별근거 exit_attribution.csv를 전체원장 TAR에 포함했습니다. 잔여 청산비용차감 평가손익 -809,436.70원, 종료가정청산 점수 +14.0257409611%입니다.

기준 BF-09-027의42회·16.7054302006977%·41,295,918.91원·MDD935만원·잔여0과 비교합니다. 기준 익절0.7%는 변경하지 않았습니다. 모든 규칙과 코드 해시는 실행 전에 등록했습니다. PF는 비용차감 완료사이클 원화 이익합/손실합 절대값이며 손실0이면 별도상태입니다.

17계약·170000USDT·한방향 한묶음·추가진입/외부입금/자동이체 없음, 기존 수수료·각레그편도2bp·롤오버 양쪽 비용을 유지합니다. 현물 충분조달, 역배 차입/비용 미검증, 다음 연속 관측분 시가 체결대용값, 분중손실/과거호가 부재, 증거금 일정 추론 한계가 있습니다. 미달 후보와 위험감소 후보를 모두 보존합니다. 탐색자료 내 결과이며 보호Final OOS·Gateway·OpenClaw·예약작업·수집기는 변경하지 않았습니다.

발동횟수 정의: 기존 exit_gap_only/exit_profit_only는 두 주요 청산조건 사이의 배타성입니다. 시간·손절·정체까지 포함한 진정한 단독/동시 발동은 strict_exit_trigger_counts.csv 및 strict_exit_trigger_ledger.csv에서 전 조건으로 분리했습니다.
