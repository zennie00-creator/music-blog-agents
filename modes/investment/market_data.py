"""시장 데이터 수집 레이어 — API 키 없이 받을 수 있는 무료 소스 사용.

- Stooq 히스토리 CSV: 지수·미국 주식·환율·금리·원자재 (기본 소스)
- 네이버 금융: 한국 개별 종목 (portfolio.md에서 `naver/000660` 형식)
- CNN Fear & Greed: 공포·탐욕 지수

히스토리를 받는 이유: ① 등락률을 전일 종가 대비로 정확히 계산,
② 신호 모듈(다이버전스·반등 품질·RS·금리 커브 등)에 추세 데이터가 필요.
워치리스트 구성은 portfolio.md(modes/investment/portfolio.py), 신호 판정은
modes/investment/signals/ 패키지가 담당한다.
"""
import ast
import csv
import io
from datetime import date, timedelta

import requests

from modes.investment import portfolio, signals
from modes.investment.indicators import rsi_series

_UA = {"User-Agent": "Mozilla/5.0 (daily-journal-agent)"}

HISTORY_DAYS = 120


def _fetch_stooq(symbol: str, days: int):
    d2 = date.today()
    d1 = d2 - timedelta(days=days)
    url = (f"https://stooq.com/q/d/l/?s={symbol}&i=d"
           f"&d1={d1.strftime('%Y%m%d')}&d2={d2.strftime('%Y%m%d')}")
    r = requests.get(url, headers=_UA, timeout=30)
    r.raise_for_status()
    rows = []
    for row in csv.DictReader(io.StringIO(r.text)):
        try:
            rows.append({
                "date": row["Date"],
                "close": float(row["Close"]),
                "volume": float(row["Volume"]) if row.get("Volume") not in (None, "", "0") else 0.0,
            })
        except (KeyError, ValueError, TypeError):
            continue
    return rows


def parse_naver_daily(text: str):
    """네이버 금융 siseJson 응답(작은따옴표 JS 배열) 파싱."""
    data = ast.literal_eval(text.strip())
    rows = []
    for row in data[1:]:  # 첫 행은 헤더
        try:
            d = str(row[0])
            rows.append({
                "date": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
                "close": float(row[4]),
                "volume": float(row[5]),
            })
        except (IndexError, ValueError, TypeError):
            continue
    return rows


def _fetch_naver(code: str, days: int):
    d2 = date.today()
    d1 = d2 - timedelta(days=days)
    url = ("https://api.finance.naver.com/siseJson.naver"
           f"?symbol={code}&requestType=1&startTime={d1.strftime('%Y%m%d')}"
           f"&endTime={d2.strftime('%Y%m%d')}&timeframe=day")
    r = requests.get(url, headers=_UA, timeout=30)
    r.raise_for_status()
    return parse_naver_daily(r.text)


def fetch_history(symbol: str, days: int = HISTORY_DAYS):
    """소스 접두사에 따라 분기해 일별 시세를 받는다 (과거→최신 순). 실패 시 []."""
    try:
        if symbol.startswith("naver/"):
            return _fetch_naver(symbol.split("/", 1)[1], days)
        return _fetch_stooq(symbol, days)
    except Exception as e:
        print(f"  ⚠️ {symbol} 히스토리 수집 실패: {e}")
        return []


def fetch_fear_greed():
    """CNN Fear & Greed 지수. 실패하면 None."""
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    try:
        r = requests.get(url, headers=_UA, timeout=30)
        r.raise_for_status()
        fg = r.json().get("fear_and_greed", {})
        return {"score": round(float(fg["score"])), "rating": fg.get("rating", "")}
    except Exception as e:
        print(f"  ⚠️ 공포·탐욕 지수 수집 실패: {e}")
        return None


def collect_context() -> dict:
    """portfolio.md 기준으로 히스토리 + 심리 지표를 수집해 신호 모듈들과 공유."""
    sections, benchmarks = portfolio.load()
    ctx = {"histories": {}, "names": {}, "sections": [], "benchmarks": benchmarks}
    for title, items in sections:
        syms = []
        for sym, name in items:
            hist = fetch_history(sym)
            if len(hist) >= 2:
                ctx["histories"][sym] = hist
                ctx["names"][sym] = name
                syms.append(sym)
        if syms:
            ctx["sections"].append((title, syms))
    ctx["fear_greed"] = fetch_fear_greed()
    return ctx


def dashboard_md(ctx) -> str:
    """자산군별 종가·등락률·거래량·RSI 대시보드 표."""
    lines = ["### 오늘의 시장 대시보드"]
    if not ctx["histories"]:
        lines.append("- (시세 데이터 수집 실패)")
    else:
        lines.append("| 구분 | 지표 | 종가 | 전일 대비 | 거래량 | RSI(14) | 기준일 |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | --- |")
        for title, syms in ctx["sections"]:
            for sym in syms:
                hist = ctx["histories"][sym]
                last, prev = hist[-1], hist[-2]
                chg = (last["close"] - prev["close"]) / prev["close"] * 100 if prev["close"] else 0.0
                vol = f"{last['volume']:,.0f}" if last["volume"] else ""
                rsi = rsi_series([r["close"] for r in hist])[-1]
                rsi_s = f"{rsi:.0f}" if rsi is not None else ""
                lines.append(f"| {title} | {ctx['names'][sym]} | {last['close']:,.2f} "
                             f"| {chg:+.2f}% | {vol} | {rsi_s} | {last['date']} |")

    fg = ctx.get("fear_greed")
    if fg:
        lines.append(f"\nCNN 공포·탐욕 지수: {fg['score']} ({fg['rating']})")
    return "\n".join(lines)


def collect() -> str:
    """대시보드 + 등록된 모든 시장 신호를 마크다운으로 반환."""
    ctx = collect_context()
    return dashboard_md(ctx) + "\n\n" + signals.run_all(ctx)
