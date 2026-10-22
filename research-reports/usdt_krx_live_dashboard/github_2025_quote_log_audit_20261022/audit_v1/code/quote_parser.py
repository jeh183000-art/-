# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: imported by audit_logs.py; no network or execution of source content.
from __future__ import annotations
import datetime as dt
import math
import re
from dataclasses import dataclass
from typing import Final, Mapping

STAMP: Final = re.compile(r"^(20\d{2}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)(?:\s*)$")
PRICE: Final = re.compile(r"(USDT 매수가|USDT 매도가|선물 매수가|선물 매도가|USD \(원화\))\s*:\s*([-+]?\d[\d,]*(?:\.\d+)?)")
PERCENT: Final = re.compile(r"([^\n]*?퍼센티지[^:]*):\s*([-+]?\d+(?:\.\d+)?)%")
KEYS: Final = ('USDT 매수가','USDT 매도가','선물 매수가','선물 매도가')
ERROR_PATTERNS: Final = (
 ('REQUEST_TOKEN_EXPIRED', re.compile(r'요청 실패(?=.*(?:token|토큰))(?=.*만료)',re.I)),
 ('REQUEST_FAILED', re.compile(r'요청.*실패|HTTPError|ConnectionError|Traceback|오류|에러')),
 ('MISSING_FUTURES_QUOTE',re.compile(r'futs_askp1.*futs_bidp1.*없')),
 ('TOKEN_EXPIRED_STATE',re.compile(r'(?:토큰|token).*만료',re.I)),
 ('MISSING_QUOTE',re.compile(r'호가.*없|데이터.*없|None|NaN')),
 ('MESSAGE_DELIVERY_FAILED',re.compile(r'메시지.*실패')),
)

@dataclass(frozen=True, slots=True)
class PriceField:
    raw_label: str
    value: float
    line_number: int

@dataclass(frozen=True, slots=True)
class LogError:
    category: str
    line_number: int
    raw_message: str

@dataclass(frozen=True, slots=True)
class Observation:
    raw_timestamp: str
    timestamp: dt.datetime
    line_start: int
    line_end: int
    fields: tuple[PriceField,...]
    percents: tuple[tuple[str,float,int],...]
    errors: tuple[LogError,...]

    def values(self) -> Mapping[str,float]:
        return {p.raw_label:p.value for p in self.fields}

    @property
    def complete_pair(self) -> bool:
        values=self.values()
        return all(k in values and math.isfinite(values[k]) and values[k]>0 for k in KEYS)

    @property
    def has_price(self) -> bool:
        return any(math.isfinite(p.value) and p.value>0 for p in self.fields)

@dataclass(frozen=True, slots=True)
class ParsedFile:
    observations: tuple[Observation,...]
    errors: tuple[LogError,...]
    lines: int
    unparsed_price_lines: tuple[int,...]
    orphan_content_lines: tuple[int,...]


def parse_log(text: str) -> ParsedFile:
    """Parse timestamp blocks without assigning quote sides, timezone or instrument identity."""
    lines=text.splitlines()
    headers=[]
    for line_number,line in enumerate(lines,1):
        match=STAMP.fullmatch(line.strip())
        if match:
            headers.append((line_number,line.strip(),dt.datetime.fromisoformat(line.strip())))
    observations=[]
    errors=[]
    unknown=[]
    orphan=[]
    for number,line in enumerate(lines,1):
        if re.search(r'(?:매수가|매도가|USD \(원화\))\s*:',line) and not PRICE.search(line):
            unknown.append(number)
        if not headers or number<headers[0][0]:
            if line.strip():orphan.append(number)
        for category,pattern in ERROR_PATTERNS:
            if pattern.search(line):
                errors.append(LogError(category,number,line));break
    for i,(start,raw,stamp) in enumerate(headers):
        end=headers[i+1][0]-1 if i+1<len(headers) else len(lines)
        fields=[]
        percents=[]
        for number in range(start+1,end+1):
            for match in PRICE.finditer(lines[number-1]):
                fields.append(PriceField(match.group(1),float(match.group(2).replace(',','')),number))
            for match in PERCENT.finditer(lines[number-1]):
                percents.append((match.group(1),float(match.group(2)),number))
        observations.append(Observation(raw,stamp,start,end,tuple(fields),tuple(percents),tuple(e for e in errors if start<=e.line_number<=end)))
    return ParsedFile(tuple(observations),tuple(errors),len(lines),tuple(unknown),tuple(orphan))


def parser_regression_checks() -> int:
    """Given complete, error-only, partial and conflicting timestamps, preserve each case."""
    fixture='2025-01-10 09:00\nUSDT 매수가: 1511, 선물 매도가: 1461.0\nUSDT 매도가: 1510, 선물 매수가: 1460.8\n2025-01-10 09:01\n요청 실패: 500 - 기간이 만료된 token 입니다.\n2025-01-10 09:02\nUSDT 매수가: 1512\n2025-01-10 09:00\nUSDT 매수가: 1513\n'
    parsed=parse_log(fixture)
    assert len(parsed.observations)==4
    assert sum(o.complete_pair for o in parsed.observations)==1
    assert parsed.observations[0].values()['선물 매수가']==1460.8
    assert parsed.observations[0].fields[0].line_number==2
    assert len(parsed.errors)==1 and parsed.errors[0].category=='REQUEST_TOKEN_EXPIRED'
    assert not parsed.observations[1].has_price
    assert parsed.observations[2].has_price and not parsed.observations[2].complete_pair
    assert parsed.observations[0].timestamp==parsed.observations[3].timestamp
    assert parsed.observations[0].values()!=parsed.observations[3].values()
    # Given a different Korean request-failure word order, When parsed, Then retain the error.
    assert len(parse_log("2025-01-10 09:00\n두 번째 API 요청에 실패했습니다.\n").errors)==1
    return 10
