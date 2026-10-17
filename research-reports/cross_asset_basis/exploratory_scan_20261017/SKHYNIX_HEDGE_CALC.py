#!/usr/bin/env python3
"""Reproduce exploratory SKHYNIX domestic-spot-long / Binance-perp-short examples.
Not a historical executable order-book backtest or a tax opinion.
Input: funding_history_20260917_20261016.csv committed alongside this script.
"""
import csv
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).with_name("funding_history_20260917_20261016.csv")
EXIT_DATE = "2026-10-16"
EXIT_FUT_OPEN_USDT = 956.93      # Binance 2026-10-16 06:30Z, 1m open
EXIT_SPOT_CLOSE_KRW = 1272000    # KRX 2026-10-16 closing auction / historical close
EXIT_USDT_KRW_PROXY = 1352       # Upbit 2026-10-16 DAILY close, not 15:30 bid
STOCK_BROKER_FEE_PER_SIDE = 0.00015  # assumed, replace per account
STOCK_SELL_TRANSFER_TAX = 0.002    # 2026 KOSPI stock sale, small individual
BINANCE_TAKER_PER_SIDE = 0.0004    # regular-user TradFi perp promo, per side

CASES = [
    ("2026-09-17_to_2026-10-16", "2026-09-17", 1745000, 1264.15, 1379),
    ("2026-10-12_to_2026-10-16", "2026-10-12", 1605000, 1206.62, 1355),
]

def as_utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def in_range(s, start, stop):
    return as_utc(start) < as_utc(s) < as_utc(stop)

def main():
    with SOURCE.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["symbol"] == "SKHYNIXUSDT"]
    for name, start_date, p0, f0, x0 in CASES:
        start = start_date + "T06:30:00+00:00"
        stop = EXIT_DATE + "T06:30:00+00:00"
        selected = [
            r for r in rows if in_range(r["funding_time_utc"], start, stop)
        ]
        funding_usdt_per_future_unit = sum(
            float(r["funding_rate_decimal"]) * float(r["mark_price_usdt"])
            for r in selected
        )
        funding_rate_simple_sum_pct = 100 * sum(
            float(r["funding_rate_decimal"]) for r in selected
        )
        # Share-matched: one KR share and short exactly one Binance future unit.
        # Notional-matched: adjust future units to identical entry KRW notional.
        for hedge_style, short_units in [
            ("share_matched", 1.0),
            ("entry_krw_notional_matched", p0 / (f0 * x0)),
        ]:
            stock_pnl_krw = EXIT_SPOT_CLOSE_KRW - p0
            fut_pnl_krw = short_units * (f0 - EXIT_FUT_OPEN_USDT) * EXIT_USDT_KRW_PROXY
            funding_krw = short_units * funding_usdt_per_future_unit * EXIT_USDT_KRW_PROXY
            stock_tax_krw = EXIT_SPOT_CLOSE_KRW * STOCK_SELL_TRANSFER_TAX
            broker_fee_krw = (p0 + EXIT_SPOT_CLOSE_KRW) * STOCK_BROKER_FEE_PER_SIDE
            fut_fee_krw = short_units * (f0 + EXIT_FUT_OPEN_USDT) * BINANCE_TAKER_PER_SIDE * EXIT_USDT_KRW_PROXY
            pnl_krw = stock_pnl_krw + fut_pnl_krw + funding_krw - stock_tax_krw - broker_fee_krw - fut_fee_krw
            print(dict(
                name=name,
                hedge_style=hedge_style,
                futures_units=round(short_units, 8),
                funding_events=len(selected),
                funding_rate_sum_pct=round(funding_rate_simple_sum_pct, 6),
                spot_pnl_krw=round(stock_pnl_krw, 2),
                futures_pnl_krw=round(fut_pnl_krw, 2),
                funding_receipts_krw=round(funding_krw, 2),
                stock_sell_tax_krw=round(stock_tax_krw, 2),
                stock_broker_fees_krw=round(broker_fee_krw, 2),
                futures_taker_fees_krw=round(fut_fee_krw, 2),
                net_before_unknown_futures_and_funding_tax_krw=round(pnl_krw, 2),
                return_on_spot_purchase_pct=round(pnl_krw / p0 * 100, 6),
                note="FX is historical daily close proxy; slippage, exchange transfers, stock dividends, futures tax unverified"
            ))

if __name__ == "__main__":
    main()
