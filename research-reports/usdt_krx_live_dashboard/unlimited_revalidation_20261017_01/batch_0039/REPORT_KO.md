# 무제한 자금 탐색 배치

연구 범위: 승인된 2026-01-01~10-15 KRX 거래일, 정규장·야간장 및 정확히 대응하는 업비트 자료. EXPLORATORY.

이 배치 조건 수: 50. 원장은 실제 관측 분봉의 다음 연속 봉 시가 대용이며 실제 호가 체결 검증 결과가 아닙니다.

기준 순위는 편도·레그별 2bp와 600_PLUS_CLEARING_ASSUMED입니다. 다른 비용·봉당 1세트 민감도는 별도 그룹입니다.

계약·자금·증거금 입장 거절은 비활성화되어 가상 현금장부가 음수가 되어도 진입합니다. 필요한 자금은 별도 위험값으로 기록합니다. 실제 대출·차입·주문은 하지 않습니다.

MDD 원화는 현금장부 기준 전체 손익의 관측 고점 대비 하락액이며 원금 비율이 아닙니다. completed_cycle_mdd_pp는 완료 사이클 수익률 누적선의 낙폭으로, 장중 위험을 대신하지 않습니다. 최대 평가손실은 미청산 세트의 현물·선물 누적 손익에서 이미 지불한 비용을 뺀 값의 최저점입니다. 미청산 평가손익에는 예상 청산비용도 별도 차감합니다.

raw 원장 숫자 row_index는 source_timestamp_index.csv의 원본 KST 시각에 대응합니다. code 1/2는 진입/청산, 3/4는 롤오버 청산/재진입, 5는 공식 정산 변동금입니다. 평가손실 통계는 별도 risk mark에서 계산하며 code 5 자체를 미실현손익으로 오인하지 않습니다.

배치 최고 조건:

```json
{
  "candidate_id": "U-052755",
  "direction": "premium_short",
  "exit_mode": "individual",
  "entry": 0.9,
  "spacing": 0.3,
  "recovery": 2.6,
  "slippage": 2.0,
  "clearing": true,
  "one_fill_per_bar": false,
  "capital_limited": false,
  "fee_policy": "600_PLUS_CLEARING_ASSUMED",
  "entry_sets": 22,
  "closed_sets": 15,
  "completed_cycles": 3,
  "cumulative_simple_return_pct": 7.279680384562928,
  "win_rate_cycles_pct": 100.0,
  "average_cycle_return_pct": 2.4265601281876426,
  "completed_cycle_mdd_pp": 0.0,
  "worst_single_cycle_return_pct": 2.3942502818156655,
  "max_open_evaluation_loss_krw": 1037297.913801998,
  "mdd_krw": 2142827.1869099964,
  "max_simultaneous_contracts": 7,
  "max_initial_margin_krw": 4672669.05,
  "max_maintenance_margin_krw": 3115112.6999999997,
  "max_gross_spot_entry_notional_krw": 103660000.0,
  "required_spot_cash_krw": 0.0,
  "required_futures_cash_krw": 5916345.148272997,
  "max_futures_adverse_krw": 2160528.331286005,
  "max_adverse_gap_pp": 2.029860515155213,
  "longest_hold_minutes": 103958,
  "residual_cycles": 1,
  "residual_sets": 7,
  "residual_unrealized_gross_krw": 1062000.0000000051,
  "residual_net_after_close_cost_krw": 882037.3872420049,
  "incomplete_cycle_net_after_close_cost_krw": 882037.3872420049,
  "fees_krw": 300998.939984,
  "slippage_krw": 268752.4,
  "funding_krw": 0,
  "total_mark_net_after_close_cost_krw": 6142583.961060002,
  "cash_rejections": 0,
  "margin_rejections": 0,
  "cap_rejections": 0,
  "stage_capacity": 10,
  "buffer_retries": 0,
  "event_capacity": 16384,
  "trade_capacity": 4096,
  "largest_cycle_share_of_positive_returns": 0.3369211741312956,
  "sample_warning": false,
  "borrow_status": "UNVERIFIED_THEORETICAL_ONLY",
  "execution_status": "NEXT_CONTINUOUS_MINUTE_OPEN_PROXY_NOT_ORDERBOOK_VERIFIED"
}
```

상위 후보는 탐색 표본에서 선택된 것으로 독립 Final OOS 성과가 아닙니다. 역배는 USDT 차입 검증이 없는 이론값이며, 잔여 손실은 누적 완료 수익률에 숨겨 합산하거나 제거하지 않습니다.
