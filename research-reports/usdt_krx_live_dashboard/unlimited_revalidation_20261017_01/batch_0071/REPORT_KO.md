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
  "candidate_id": "U-019360",
  "direction": "discount_long",
  "exit_mode": "fixed_basket",
  "entry": 2.0,
  "spacing": 0.2,
  "recovery": 3.2,
  "slippage": 2.0,
  "clearing": true,
  "one_fill_per_bar": false,
  "capital_limited": false,
  "fee_policy": "600_PLUS_CLEARING_ASSUMED",
  "entry_sets": 13,
  "closed_sets": 13,
  "completed_cycles": 3,
  "cumulative_simple_return_pct": 9.41458924119744,
  "win_rate_cycles_pct": 100.0,
  "average_cycle_return_pct": 3.13819641373248,
  "completed_cycle_mdd_pp": 0.0,
  "worst_single_cycle_return_pct": 2.7719174385411143,
  "max_open_evaluation_loss_krw": 1918386.5415569893,
  "mdd_krw": 4564999.999999996,
  "max_simultaneous_contracts": 11,
  "max_initial_margin_krw": 8784654.45,
  "max_maintenance_margin_krw": 5856436.3,
  "max_gross_spot_entry_notional_krw": 161350000.0,
  "required_spot_cash_krw": 161253546.0,
  "required_futures_cash_krw": 13998753.546690991,
  "max_futures_adverse_krw": 5214099.096690992,
  "max_adverse_gap_pp": 2.212695691840438,
  "longest_hold_minutes": 140600,
  "residual_cycles": 0,
  "residual_sets": 0,
  "residual_unrealized_gross_krw": 0.0,
  "residual_net_after_close_cost_krw": 0.0,
  "incomplete_cycle_net_after_close_cost_krw": 0,
  "fees_krw": 246602.5384949998,
  "slippage_krw": 354634.99999999994,
  "funding_krw": 0,
  "total_mark_net_after_close_cost_krw": 6665762.46150499,
  "cash_rejections": 0,
  "margin_rejections": 0,
  "cap_rejections": 0,
  "stage_capacity": 14,
  "buffer_retries": 0,
  "event_capacity": 16384,
  "trade_capacity": 4096,
  "largest_cycle_share_of_positive_returns": 0.3854244852288229,
  "sample_warning": false,
  "borrow_status": "NOT_APPLICABLE",
  "execution_status": "NEXT_CONTINUOUS_MINUTE_OPEN_PROXY_NOT_ORDERBOOK_VERIFIED"
}
```

상위 후보는 탐색 표본에서 선택된 것으로 독립 Final OOS 성과가 아닙니다. 역배는 USDT 차입 검증이 없는 이론값이며, 잔여 손실은 누적 완료 수익률에 숨겨 합산하거나 제거하지 않습니다.
