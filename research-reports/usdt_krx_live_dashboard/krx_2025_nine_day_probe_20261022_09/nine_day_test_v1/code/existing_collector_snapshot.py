from __future__ import annotations

import csv
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


HERE = Path(__file__).resolve().parent
if HERE.name == "work":
    ROOT = HERE.parent
    PROJECT = ROOT / "outputs" / "usdt_krx_live_dashboard"
else:
    PROJECT = HERE.parents[1]
    ROOT = PROJECT.parents[1]
OUT = PROJECT / "data" / "krx_2025_full_1m"
KRX_ARCHIVE = PROJECT / "data" / "archive_2025_2026" / "krx_daily" / "raw"
PROBE = OUT / "probe"
OLD_BARS = PROJECT / "data" / "krx_1m_month_2025" / "krx_bars"
BASE = "https://openapi.koreainvestment.com:9443"
KIS_URL = BASE + "/uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice"
KRX_URL = "https://data-dbg.krx.co.kr/svc/apis/drv/fut_bydd_trd"
BAR_FIELDS = [
    "trade_date", "time_kst", "contract_code_kis", "contract_code_krx",
    "contract_month", "open", "high", "low", "close", "volume",
    "cumulative_turnover_krw", "source",
]
MONTHS = [f"2025{m:02d}" for m in range(1, 13)]
sys.path.insert(0, str(PROJECT))
from krx_live.config import KIS_APP_KEY, KIS_APP_SECRET, KRX_API_KEY  # noqa: E402


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def get_krx_rows(day: str) -> list[dict[str, Any]]:
    cached = KRX_ARCHIVE / f"{day}.json"
    if cached.exists():
        rows = read_json(cached)
        regular = [r for r in rows if r.get("PROD_NM") == "미국달러 선물" and r.get("MKT_NM") == "정규"]
        if regular or day != "20261015":
            return regular
    if not KRX_API_KEY:
        raise RuntimeError(f"KRX official daily data missing for {day}; local KRX API key unavailable")
    response = requests.get(KRX_URL, headers={"AUTH_KEY": KRX_API_KEY}, params={"basDd": day}, timeout=30)
    body = response.json()
    if response.status_code != 200:
        raise RuntimeError(f"KRX daily API HTTP {response.status_code} for {day}")
    rows = body.get("OutBlock_1", []) or []
    save_path = OUT / "krx_daily_raw" / f"{day}.json"
    write_json(save_path, rows)
    return [r for r in rows if r.get("PROD_NM") == "미국달러 선물" and r.get("MKT_NM") == "정규"]


def front_contract(day: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    contracts: list[tuple[str, int, dict[str, Any]]] = []
    for row in rows:
        match = re.search(r"(20\d{4})", str(row.get("ISU_NM", "")))
        volume = int(row.get("ACC_TRDVOL") or 0)
        if match and volume > 0 and row.get("TDD_CLSPRC"):
            contracts.append((match.group(1), volume, row))
    if not contracts:
        return None
    month, volume, row = min(contracts, key=lambda item: item[0])
    krx_code = row["ISU_CD"]
    if krx_code.startswith("175W"):
        kis_code = f"175W{month[-2:]}"
    elif krx_code.startswith("A756"):
        kis_code = f"A756{month[-2:]}"
    else:
        kis_code = ""
    return {
        "date": day,
        "contract_month": month,
        "contract_code_krx": krx_code,
        "contract_code_kis": kis_code,
        "contract_name": row["ISU_NM"],
        "official_volume": volume,
        "official_close": row["TDD_CLSPRC"],
        "official_settlement": row.get("SETL_PRC", ""),
        "krx_market": row.get("MKT_NM", ""),
    }


def official_daily_map() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    selected: dict[str, dict[str, Any]] = {}
    last_trade_day: dict[str, str] = {}
    paths = sorted(KRX_ARCHIVE.glob("2025*.json"))
    for path in paths:
        day = path.stem
        if not ("20250101" <= day <= "20251231"):
            continue
        try:
            rows = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        front = front_contract(day, [r for r in rows if r.get("PROD_NM") == "미국달러 선물" and r.get("MKT_NM") == "정규"])
        if front:
            selected[day] = front
            last_trade_day[front["contract_month"]] = day
    day = "20251231"
    if day not in selected:
        rows = get_krx_rows(day)
        front = front_contract(day, rows)
        if front:
            selected[day] = front
            last_trade_day[front["contract_month"]] = day
    expiry_path = PROJECT / "data" / "archive_2025_2026" / "krx_daily" / "contract_master.csv"
    expiry_by_month = {}
    if expiry_path.exists():
        for row in read_csv(expiry_path):
            if row.get("contract_month") and row.get("expiry_date"):
                expiry_by_month[row["contract_month"].replace("-", "")] = row["expiry_date"]
    for contract in selected.values():
        contract["expiry_date"] = expiry_by_month.get(contract["contract_month"], "")
    return selected, last_trade_day


def normalize_existing(path: Path, contract: dict[str, Any], source: str) -> list[dict[str, Any]]:
    input_rows = read_csv(path)
    rows: list[dict[str, Any]] = []
    for row in input_rows:
        date = str(row.get("trade_date", contract["date"])).replace("-", "")
        time_kst = str(row.get("time_kst", row.get("stck_cntg_hour", ""))).zfill(6)
        krx_code = str(row.get("contract_code_krx", contract["contract_code_krx"]))
        kis_code = str(row.get("contract_code_kis", contract["contract_code_kis"]))
        contract_month = str(row.get("contract_month", contract["contract_month"]))
        rows.append({
            "trade_date": date,
            "time_kst": time_kst,
            "contract_code_kis": kis_code,
            "contract_code_krx": krx_code,
            "contract_month": contract_month,
            "open": row.get("open", row.get("futs_oprc", "")),
            "high": row.get("high", row.get("futs_hgpr", "")),
            "low": row.get("low", row.get("futs_lwpr", "")),
            "close": row.get("close", row.get("futs_prpr", "")),
            "volume": row.get("volume", row.get("cntg_vol", "")),
            "cumulative_turnover_krw": row.get("cumulative_turnover_krw", row.get("acml_tr_pbmn", "")),
            "source": source,
        })
    return rows


def validate_bars(rows: list[dict[str, Any]], contract: dict[str, Any], last_trade_day: dict[str, str]) -> dict[str, Any]:
    keyed: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for row in rows:
        if row["trade_date"] != contract["date"]:
            continue
        if row["contract_code_kis"] != contract["contract_code_kis"] or row["contract_code_krx"] != contract["contract_code_krx"]:
            return {"ok": False, "reason": "contract_code_mismatch", "rows": 0, "bars": []}
        stamp = row["time_kst"]
        if stamp in keyed:
            duplicates += 1
        keyed[stamp] = row
    bars = [keyed[k] for k in sorted(keyed)]
    ohlc_errors = 0
    for row in bars:
        op, high, low, close = (number(row[k]) for k in ("open", "high", "low", "close"))
        if None in (op, high, low, close) or high < max(op, close) or low > min(op, close) or high < low:
            ohlc_errors += 1
    last_close = number(bars[-1]["close"]) if bars else None
    daily_close = number(contract["official_close"])
    close_match = last_close is not None and daily_close is not None and abs(last_close - daily_close) <= 0.100001
    expected_end = "113000" if contract.get("expiry_date") == f"{contract['date'][:4]}-{contract['date'][4:6]}-{contract['date'][6:8]}" else "154500"
    expected_start = "094500" if contract["date"] == "20250102" else "084500"
    session_end_match = bool(bars and bars[-1]["time_kst"] == expected_end)
    ok = bool(bars and bars[0]["time_kst"] == expected_start and ohlc_errors == 0 and close_match and session_end_match)
    return {
        "ok": ok,
        "reason": "" if ok else ";".join(x for x, bad in [
            ("no_rows", not bars),
            ("first_time_mismatch", bool(bars) and bars[0]["time_kst"] != expected_start),
            ("ohlc_invalid", ohlc_errors > 0),
            ("daily_close_mismatch", not close_match),
            ("session_end_mismatch", not session_end_match),
        ] if bad),
        "bars": bars,
        "rows": len(bars),
        "duplicates": duplicates,
        "ohlc_errors": ohlc_errors,
        "first_time": bars[0]["time_kst"] if bars else "",
        "expected_start": expected_start,
        "last_time": bars[-1]["time_kst"] if bars else "",
        "first_close": bars[0]["close"] if bars else "",
        "last_close": bars[-1]["close"] if bars else "",
        "official_close": contract["official_close"],
        "close_match": close_match,
        "expected_end": expected_end,
    }


def token() -> tuple[str | None, dict[str, Any]]:
    if not KIS_APP_KEY or not KIS_APP_SECRET:
        return None, {"success": False, "http_status": None, "message": "KIS credentials absent"}
    response = requests.post(BASE + "/oauth2/tokenP", json={
        "grant_type": "client_credentials", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET,
    }, timeout=25)
    body = response.json()
    access = body.get("access_token")
    return access, {
        "success": bool(access),
        "http_status": response.status_code,
        "error_code": body.get("error_code", ""),
        "error_description": str(body.get("error_description", ""))[:200],
    }


def fetch_day(contract: dict[str, Any], headers: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    day = contract["date"]
    cursor = "154500"
    seen_cursors: set[str] = set()
    rows: dict[str, dict[str, Any]] = {}
    calls: list[dict[str, Any]] = []
    error = ""
    for page in range(7):
        if cursor in seen_cursors:
            error = "pagination_cursor_repeated"
            break
        seen_cursors.add(cursor)
        if page:
            time.sleep(1.1)
        params = {
            "FID_COND_MRKT_DIV_CODE": "CF",
            "FID_INPUT_ISCD": contract["contract_code_kis"],
            "FID_HOUR_CLS_CODE": "60",
            "FID_PW_DATA_INCU_YN": "Y",
            "FID_FAKE_TICK_INCU_YN": "N",
            "FID_INPUT_DATE_1": day,
            "FID_INPUT_HOUR_1": cursor,
        }
        response = requests.get(KIS_URL, params=params, headers=headers, timeout=30)
        try:
            body = response.json()
        except ValueError:
            body = {}
        output = body.get("output2", []) or []
        day_rows = [r for r in output if str(r.get("stck_bsop_date", "")) == day]
        calls.append({"page": page + 1, "cursor": cursor, "http_status": response.status_code,
                      "rt_cd": body.get("rt_cd", ""), "msg_cd": body.get("msg_cd", ""),
                      "msg1": str(body.get("msg1", ""))[:200], "rows": len(day_rows)})
        if response.status_code != 200 or str(body.get("rt_cd", "")) != "0":
            error = f"HTTP_{response.status_code}_rt_cd_{body.get('rt_cd', '')}_msg_cd_{body.get('msg_cd', '')}"
            break
        for item in day_rows:
            stamp = str(item.get("stck_cntg_hour", ""))
            if stamp:
                rows[stamp] = {
                    "trade_date": day,
                    "time_kst": stamp,
                    "contract_code_kis": contract["contract_code_kis"],
                    "contract_code_krx": contract["contract_code_krx"],
                    "contract_month": contract["contract_month"],
                    "open": item.get("futs_oprc", ""),
                    "high": item.get("futs_hgpr", ""),
                    "low": item.get("futs_lwpr", ""),
                    "close": item.get("futs_prpr", ""),
                    "volume": item.get("cntg_vol", ""),
                    "cumulative_turnover_krw": item.get("acml_tr_pbmn", ""),
                    "source": "KIS_FHKIF03020200",
                }
        times = [str(r.get("stck_cntg_hour", "")) for r in day_rows if r.get("stck_cntg_hour")]
        if not times or min(times) <= "084500":
            break
        next_cursor = (datetime.strptime(min(times), "%H%M%S") - timedelta(minutes=1)).strftime("%H%M%S")
        if next_cursor >= cursor:
            error = "pagination_cursor_not_decreasing"
            break
        cursor = next_cursor
    else:
        error = "pagination_page_limit_reached"
    return [rows[k] for k in sorted(rows)], {"calls": calls, "error": error}


def existing_candidates(contract: dict[str, Any]) -> list[tuple[Path, str]]:
    day = contract["date"]
    kis = contract["contract_code_kis"]
    options = [
        (PROBE / f"{day}_{kis}_1m.csv", "verified_probe_reuse"),
        (OLD_BARS / f"{day}_{kis}_regular.csv", "verified_monthly_reuse"),
    ]
    return [(path, source) for path, source in options if path.exists()]


def day_output_paths(day: str, kis: str) -> tuple[Path, Path]:
    return OUT / "bars" / f"{day}_{kis}_regular.csv", OUT / "status" / f"{day}_regular.json"


def save_day(contract: dict[str, Any], bars: list[dict[str, Any]], status: dict[str, Any]) -> None:
    bar_path, status_path = day_output_paths(contract["date"], contract["contract_code_kis"])
    write_csv(bar_path, bars, BAR_FIELDS)
    write_json(status_path, {**contract, **{k: v for k, v in status.items() if k != "bars"},
                             "bar_file": str(bar_path.relative_to(OUT)),
                             "retrieved_utc": datetime.now(timezone.utc).isoformat()})


def load_saved_day(contract: dict[str, Any], last_trade_day: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    bar_path, status_path = day_output_paths(contract["date"], contract["contract_code_kis"])
    if not bar_path.exists() or not status_path.exists():
        return None
    prior = read_json(status_path)
    if prior.get("status") not in {"COMPLETE", "PARTIAL"} or prior.get("contract_code_krx") != contract["contract_code_krx"]:
        return None
    result = validate_bars(read_csv(bar_path), contract, last_trade_day)
    usable_partial = bool(result.get("rows") and result.get("close_match") and result.get("ohlc_errors") == 0)
    return (result["bars"], result) if result["ok"] or usable_partial else None


def make_month(month: str, selected: dict[str, dict[str, Any]], last_trade_day: dict[str, str]) -> dict[str, Any]:
    month_days = [d for d in sorted(selected) if d.startswith(month)]
    records: list[dict[str, Any]] = []
    contracts: list[dict[str, Any]] = []
    for day in month_days:
        contract = selected[day]
        saved = load_saved_day(contract, last_trade_day)
        if saved:
            bars, validation = saved
            reused_status = "COMPLETE" if validation["ok"] else "PARTIAL"
            save_day(contract, bars, {**validation, "status": reused_status, "source": "resumed_existing_output",
                     "pages": 0, "api_calls": [], "api_error": ""})
            records.append({**contract, **{k: v for k, v in validation.items() if k != "bars"},
                            "status": reused_status, "source": "resumed_existing_output", "pages": 0,
                            "http_status": "", "rt_cd": "", "msg_cd": "", "api_error": ""})
            contracts.append(contract)
            continue
        reused = None
        reuse_source = ""
        for path, source in existing_candidates(contract):
            candidate = normalize_existing(path, contract, source)
            validation = validate_bars(candidate, contract, last_trade_day)
            usable_partial = bool(validation.get("rows") and validation.get("close_match") and validation.get("ohlc_errors") == 0)
            if validation["ok"] or usable_partial:
                reused = validation["bars"]
                reuse_source = source
                break
        api_meta: dict[str, Any] = {"calls": [], "error": ""}
        http_status: Any = ""
        rt_cd: Any = ""
        msg_cd: Any = ""
        if reused is not None:
            bars = reused
            validation = validate_bars(bars, contract, last_trade_day)
            status = "COMPLETE" if validation["ok"] else "PARTIAL"
            source = reuse_source
        else:
            bars = []
            validation = {"ok": False, "reason": "not_attempted", "bars": []}
            status = "API_ERROR"
            source = "KIS_FHKIF03020200"
            for attempt in range(3):
                try:
                    fetched, api_meta = fetch_day(contract, make_month.headers)
                    bars = fetched
                    validation = validate_bars(bars, contract, last_trade_day)
                    api_calls = api_meta.get("calls", [])
                    http_status = api_calls[-1].get("http_status", "") if api_calls else ""
                    rt_cd = api_calls[-1].get("rt_cd", "") if api_calls else ""
                    msg_cd = api_calls[-1].get("msg_cd", "") if api_calls else ""
                    if validation["ok"]:
                        status = "COMPLETE"
                        break
                    status = "HISTORY_UNAVAILABLE" if not bars and not api_meta.get("error") else "PARTIAL"
                except requests.RequestException as exc:
                    api_meta = {"calls": [], "error": type(exc).__name__}
                    status = "REQUEST_ERROR"
                if attempt < 2:
                    time.sleep(2.0 * (attempt + 1))
            if status == "COMPLETE":
                save_day(contract, validation["bars"], {**validation, "status": status,
                         "source": source, "pages": len(api_meta.get("calls", [])),
                         "api_calls": api_meta.get("calls", []), "api_error": ""})
            else:
                save_day(contract, bars, {**validation, "status": status,
                         "source": source, "pages": len(api_meta.get("calls", [])),
                         "api_calls": api_meta.get("calls", []), "api_error": api_meta.get("error", validation.get("reason", ""))})
        if reused is not None:
            save_day(contract, bars, {**validation, "status": status, "source": source,
                     "pages": 0, "api_calls": [], "api_error": ""})
        records.append({**contract, **{k: v for k, v in validation.items() if k != "bars"},
                        "status": status, "source": source,
                        "pages": len(api_meta.get("calls", [])),
                        "http_status": http_status, "rt_cd": rt_cd, "msg_cd": msg_cd,
                        "api_error": api_meta.get("error", validation.get("reason", "")),
                        "api_calls": json.dumps(api_meta.get("calls", []), ensure_ascii=False)})
        contracts.append(contract)
        progress = {
            "current_month": month,
            "last_completed_date": day,
            "completed_months": [m for m in MONTHS if (OUT / "monthly" / f"KRX_USD_1m_{m}.csv").exists()],
            "updated_utc": datetime.now(timezone.utc).isoformat(),
        }
        write_json(OUT / "progress.json", progress)
    month_bars: list[dict[str, Any]] = []
    for day in month_days:
        contract = selected[day]
        bar_path, _ = day_output_paths(day, contract["contract_code_kis"])
        if bar_path.exists():
            month_bars.extend(read_csv(bar_path))
    month_bars.sort(key=lambda row: (row["trade_date"], row["time_kst"]))
    write_csv(OUT / "monthly" / f"KRX_USD_1m_{month[:4]}_{month[4:]}.csv", month_bars, BAR_FIELDS)
    write_csv(OUT / "monthly" / f"KRX_USD_1m_{month[:4]}_{month[4:]}_date_status.csv", records)
    success = sum(row["status"] == "COMPLETE" for row in records)
    month_status = "COMPLETE" if success == len(month_days) and month_days else "PARTIAL"
    summary = {
        "month": month,
        "trading_days": len(month_days),
        "successful_days": success,
        "minute_bars": len(month_bars),
        "missing_dates": [{"date": row["date"], "reason": row.get("api_error") or row.get("reason", "")} for row in records if row["status"] != "COMPLETE"],
        "close_matches": sum(row.get("close_match") is True or row.get("close_match") == "True" for row in records),
        "close_mismatches": sum(row.get("close_match") is False or row.get("close_match") == "False" for row in records),
        "status": month_status,
        "contracts": sorted({f"{c['contract_month']}:{c['contract_code_krx']}:{c['contract_code_kis']}" for c in contracts}),
        "updated_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(OUT / "monthly" / f"{month}_summary.json", summary)
    summary_rows = []
    for m in MONTHS:
        p = OUT / "monthly" / f"{m}_summary.json"
        if p.exists():
            x = read_json(p)
            summary_rows.append(x)
    write_csv(OUT / "monthly_results.csv", summary_rows)
    progress = {
        "current_month": month,
        "completed_months": [x["month"] for x in summary_rows],
        "last_completed_date": month_days[-1] if month_days else "",
        "updated_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(OUT / "progress.json", progress)
    return summary


def initialize_headers() -> tuple[dict[str, str] | None, dict[str, Any]]:
    access, auth = token()
    if not access:
        return None, auth
    return {
        "authorization": "Bearer " + access,
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": "FHKIF03020200",
        "custtype": "P",
        "content-type": "application/json",
    }, auth


def main() -> None:
    if len(sys.argv) != 2 or (sys.argv[1] not in MONTHS and sys.argv[1] != "probe-and-january"):
        raise SystemExit("Usage: krx_2025_month_collector.py YYYYMM|probe-and-january")
    mode = sys.argv[1]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "bars").mkdir(exist_ok=True)
    (OUT / "status").mkdir(exist_ok=True)
    (OUT / "monthly").mkdir(exist_ok=True)
    (OUT / "probe").mkdir(exist_ok=True)
    selected, last_trade_day = official_daily_map()
    headers, auth = initialize_headers()
    if headers is None:
        write_json(OUT / "auth_status.json", {**auth, "secrets_written_or_printed": False})
        print(json.dumps({"month": mode, "status": "AUTH_ERROR", "http_status": auth.get("http_status"), "error": auth.get("error_code", "")}, ensure_ascii=False))
        raise SystemExit(2)
    make_month.headers = headers
    write_json(OUT / "auth_status.json", {"success": True, "http_status": auth.get("http_status"), "secrets_written_or_printed": False,
                                           "updated_utc": datetime.now(timezone.utc).isoformat()})
    if mode == "probe-and-january":
        test_dates = ["20250115", "20250915", "20251013"]
        probes = []
        for index, day in enumerate(test_dates):
            contract = selected.get(day)
            if contract is None:
                probes.append({"date": day, "status": "KRX_OFFICIAL_DATA_MISSING"})
                continue
            if index:
                time.sleep(1.1)
            fetched, meta = fetch_day(contract, headers)
            checked = validate_bars(fetched, contract, last_trade_day)
            status = "DATA_READY" if checked["ok"] else ("HISTORY_UNAVAILABLE" if not fetched and not meta.get("error") else "PARTIAL")
            if fetched:
                write_csv(PROBE / f"{day}_{contract['contract_code_kis']}_1m.csv", fetched, BAR_FIELDS)
            probes.append({**contract, "status": status,
                           "http_status": meta["calls"][-1]["http_status"] if meta.get("calls") else "",
                           "rt_cd": meta["calls"][-1]["rt_cd"] if meta.get("calls") else "",
                           "msg_cd": meta["calls"][-1]["msg_cd"] if meta.get("calls") else "",
                           "rows": checked.get("rows", 0), "first_time": checked.get("first_time", ""),
                           "last_time": checked.get("last_time", ""), "last_close": checked.get("last_close", ""),
                           "official_close": contract["official_close"], "close_match": checked.get("close_match", False),
                           "duplicates": checked.get("duplicates", 0), "ohlc_errors": checked.get("ohlc_errors", 0),
                           "reason": checked.get("reason", meta.get("error", "")),
                           "api_calls": meta.get("calls", [])})
        write_json(OUT / "probe" / "probe_results.json", {"provider": "KIS Open API", "tr_id": "FHKIF03020200", "tests": probes,
                                                            "secrets_written_or_printed": False,
                                                            "updated_utc": datetime.now(timezone.utc).isoformat()})
        write_csv(OUT / "probe" / "probe_results.csv", probes)
        jan = next((row for row in probes if row.get("date") == "20250115"), {})
        if jan.get("status") != "DATA_READY":
            print(json.dumps({"probe_results": [{k: v for k, v in row.items() if k != "api_calls"} for row in probes],
                              "january_collection_started": False}, ensure_ascii=False))
            raise SystemExit(3)
        summary = make_month("202501", selected, last_trade_day)
        print(json.dumps({"probe_results": [{k: v for k, v in row.items() if k != "api_calls"} for row in probes],
                          "january_summary": summary}, ensure_ascii=False))
    else:
        summary = make_month(mode, selected, last_trade_day)
        print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
