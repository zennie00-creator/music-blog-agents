"""분기 재무 시계열 — SEC EDGAR(XBRL) 공개 API.

뉴스는 '무슨 일이 있었나'를 알려주지만 '숫자가 어떻게 변해왔나'는 답하지 못한다.
Rule of 40이 전분기·1년 전 대비 어떤지 같은 질문은 재무 시계열이 있어야 한다.

SEC EDGAR는 키 없이 분기별 XBRL 값을 준다(User-Agent에 연락처만 요구).
매출·영업이익을 뽑아 YoY 성장률과 영업마진을 계산하고, 참고용으로
'성장률+마진'(Rule of 40 계열 지표)을 함께 낸다.

주의: Rule of 40의 마진 정의는 회사·애널리스트마다 다르다(FCF 마진 vs 영업마진,
GAAP vs adjusted). 여기 값은 GAAP 영업마진 기준이므로 보도 수치와 다를 수 있고,
그 점을 표에 명시한다.
"""
import json
import re

import requests

# SEC 정책상 User-Agent에 식별 가능한 연락처가 있어야 한다.
_UA = {"User-Agent": "invest-journal-bot (personal research; contact via github)",
       "Accept-Encoding": "gzip, deflate"}

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_CONCEPT = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"

# 회사마다 쓰는 XBRL 태그가 달라 순서대로 시도한다.
_REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
]
_OPINC_TAGS = ["OperatingIncomeLoss"]

_cik_cache = None


def _cik(ticker: str):
    """티커 → 10자리 CIK. 실패 시 None."""
    global _cik_cache
    if _cik_cache is None:
        r = requests.get(_TICKERS_URL, headers=_UA, timeout=15)
        r.raise_for_status()
        _cik_cache = {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                      for v in r.json().values()}
    return _cik_cache.get(ticker.upper())


def _concept(cik: str, tags):
    """태그 후보를 순서대로 시도해 분기 값 목록을 얻는다 → [{end, val, fy, fp}]."""
    for tag in tags:
        try:
            r = requests.get(_CONCEPT.format(cik=cik, tag=tag), headers=_UA, timeout=15)
            if not r.ok:
                continue
            units = r.json().get("units", {}).get("USD", [])
        except Exception:
            continue
        # 분기(약 3개월) 데이터만: start~end 간격으로 판별, 10-Q/10-K 원본만
        rows = []
        for u in units:
            if not (u.get("start") and u.get("end") and u.get("val") is not None):
                continue
            try:
                days = (_d(u["end"]) - _d(u["start"])).days
            except Exception:
                continue
            if 60 <= days <= 100:      # 한 분기
                rows.append({"end": u["end"], "val": float(u["val"]),
                             "fy": u.get("fy"), "fp": u.get("fp")})
        if rows:
            # 같은 종료일 중복(정정 공시)은 마지막 것만
            dedup = {}
            for r_ in sorted(rows, key=lambda x: x["end"]):
                dedup[r_["end"]] = r_
            return sorted(dedup.values(), key=lambda x: x["end"])
    return []


def _d(s):
    from datetime import date
    return date.fromisoformat(s)


def quarterly_table(ticker: str, quarters: int = 6):
    """→ (표 마크다운, 비어있으면 ''). 매출·YoY·영업마진·(성장률+마진)."""
    cik = _cik(ticker)
    if not cik:
        return ""
    rev = _concept(cik, _REVENUE_TAGS)
    if len(rev) < 2:
        return ""
    opi = {r["end"]: r["val"] for r in _concept(cik, _OPINC_TAGS)}
    by_end = {r["end"]: r["val"] for r in rev}

    lines = [f"**{ticker} 분기 재무 (SEC EDGAR, GAAP)**",
             "| 분기종료 | 매출 | YoY | 영업마진 | 성장률+마진 |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for r in rev[-quarters:]:
        end, val = r["end"], r["val"]
        # 1년 전 같은 분기(±20일)를 찾아 YoY 계산
        target = f"{int(end[:4]) - 1}{end[4:]}"
        prior = min(by_end, key=lambda e: abs((_d(e) - _d(target)).days), default=None)
        yoy = None
        if prior and abs((_d(prior) - _d(target)).days) <= 20 and by_end[prior]:
            yoy = (val / by_end[prior] - 1) * 100
        margin = (opi[end] / val * 100) if end in opi and val else None
        r40 = (yoy + margin) if (yoy is not None and margin is not None) else None
        lines.append(
            f"| {end} | ${val / 1e9:,.2f}B | "
            f"{f'{yoy:+.0f}%' if yoy is not None else '—'} | "
            f"{f'{margin:+.0f}%' if margin is not None else '—'} | "
            f"{f'{r40:.0f}' if r40 is not None else '—'} |")
    lines.append("(성장률+마진은 Rule of 40 계열 참고치 — GAAP 영업마진 기준이라 "
                 "FCF·adjusted 기준 보도 수치와 다를 수 있음)")
    return "\n".join(lines)


def tickers_in(text: str, limit: int = 2):
    """질문에 언급된 워치리스트 종목의 미국 티커를 찾는다."""
    from modes.investment import portfolio
    sections, _ = portfolio.load()
    found = []
    for _sec, items in sections:
        for sym, name in items:
            bare = sym.split("/")[-1].split(":")[-1]
            if not bare.isalpha():
                continue  # 지수·한국코드 등 제외
            # \b는 한글을 단어 문자로 봐서 'PLTR의'를 못 잡는다 → 영문 경계로 판정
            hit = (re.search(rf"(?<![A-Za-z]){re.escape(bare)}(?![A-Za-z])", text, re.I)
                   or (name and name.split("(")[0].strip() in text))
            if hit and bare.upper() not in found:
                found.append(bare.upper())
    return found[:limit]


def context_for(question: str) -> str:
    """질문에 언급된 종목의 재무 시계열 블록. 없으면 ''."""
    out = []
    for t in tickers_in(question):
        try:
            tbl = quarterly_table(t)
        except Exception as e:
            print(f"  ⚠️ SEC 재무 조회 실패 {t}: {e}")
            continue
        if tbl:
            out.append(tbl)
            print(f"  📊 SEC 분기 재무 {t}")
    if not out:
        return ""
    return ("아래는 질문에 언급된 종목의 분기 재무 추이입니다 (SEC EDGAR 공시 기준):\n\n"
            + "\n\n".join(out))
