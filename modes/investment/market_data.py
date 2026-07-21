"""시장 데이터 수집 레이어 — API 키 없이 받을 수 있는 무료 소스 사용.

소스는 portfolio.md의 심볼 접두사로 자동 분기한다:
- (접두사 없음) Yahoo Finance: 지수·미국 주식·환율·금·BTC (거래량 제공)
- `fred/DGS10`  FRED(세인트루이스 연준): 국채 금리 (거래량 개념 없음)
- `naver/000660` 네이버 금융: 한국 개별 종목

  ※ stooq는 봇 차단(JS 검증)으로 폐기 (2026-07). Yahoo는 브라우저 UA 필요.

- CNN Fear & Greed: 공포·탐욕 지수

히스토리를 받는 이유: ① 등락률을 전일 종가 대비로 정확히 계산,
② 신호 모듈(다이버전스·반등 품질·RS·금리 커브 등)에 추세 데이터가 필요.
워치리스트 구성은 portfolio.md(modes/investment/portfolio.py), 신호 판정은
modes/investment/signals/ 패키지가 담당한다.
"""
import ast
import csv
import io
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone

import requests

from modes.investment import charts, portfolio, sheet_source, signals
from modes.investment.indicators import rsi_series

# Yahoo·FRED는 봇 요청에 브라우저 User-Agent를 요구한다.
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

HISTORY_DAYS = 120

# CBOE 금리 지수 (Yahoo 제공) — 구글시트 GOOGLEFINANCE("INDEXCBOE:TNX")/10 과
# 같은 원천. 값이 금리×10으로 나오는 경우가 있어 fetch 시 자동 정규화한다.
# FRED(DGS)와 달리 당일 마감치가 바로 나온다 (FRED는 영업일 1일 지연).
YIELD_INDEX_SYMBOLS = {"^IRX", "^FVX", "^TNX", "^TYX"}


def _normalize_yield(rows):
    """CBOE 금리 지수의 ×10 표기 자동 보정 (금리가 15%를 넘을 일은 없다)."""
    closes = [r["close"] for r in rows if r["close"]]
    if closes and sum(closes) / len(closes) > 15:
        for r in rows:
            r["close"] = r["close"] / 10
    return rows


# 다수 심볼을 연속 호출하면 Yahoo가 429(rate limit)를 줄 수 있어
# 두 호스트를 폴백으로 두고 짧게 재시도한다.
_YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")


def _yahoo_get(quoted: str, rng: str):
    last_err = None
    for attempt in range(2):
        for host in _YAHOO_HOSTS:
            url = (f"https://{host}/v8/finance/chart/{quoted}"
                   f"?interval=1d&range={rng}")
            try:
                r = requests.get(url, headers=_UA, timeout=30)
                if r.status_code == 429:
                    last_err = requests.HTTPError("429 Too Many Requests")
                    continue
                r.raise_for_status()
                return r.json()
            except requests.RequestException as e:
                last_err = e
        time.sleep(1.5 * (attempt + 1))  # 백오프 후 재시도
    raise last_err


def _fetch_yahoo(symbol: str, days: int):
    """Yahoo Finance v8 chart API. 지수/종목/환율/금/BTC + 거래량."""
    rng = "1y" if days > 180 else "6mo"
    quoted = urllib.parse.quote(symbol, safe="")
    result = _yahoo_get(quoted, rng)["chart"]["result"][0]
    ts = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    closes = quote.get("close") or []
    vols = quote.get("volume") or []
    rows = []
    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        v = vols[i] if i < len(vols) else None
        d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append({"date": d, "close": float(c), "volume": float(v) if v else 0.0})
    return rows


def _fetch_fred(series: str, days: int):
    """FRED CSV — 국채 금리 등 매크로 시계열 (무키, 거래량 없음)."""
    cosd = (date.today() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={cosd}"
    r = requests.get(url, headers=_UA, timeout=30)
    r.raise_for_status()
    reader = csv.reader(io.StringIO(r.text))
    next(reader, None)  # 헤더: observation_date,SERIES
    rows = []
    for row in reader:
        if len(row) < 2 or row[1] in (".", ""):
            continue
        try:
            rows.append({"date": row[0], "close": float(row[1]), "volume": 0.0})
        except ValueError:
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
        if symbol.startswith("gsheet/"):
            return sheet_source.history_for(symbol.split("/", 1)[1])
        if symbol.startswith("naver/"):
            return _fetch_naver(symbol.split("/", 1)[1], days)
        if symbol.startswith("fred/"):
            return _fetch_fred(symbol.split("/", 1)[1], days)
        rows = _fetch_yahoo(symbol, days)
        if symbol in YIELD_INDEX_SYMBOLS:
            rows = _normalize_yield(rows)
        return rows
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
    sheet_source.refresh()  # 구글시트 스냅숏 1회 수집 + 이력 누적 (gsheet/ 심볼용)
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
        lines.append("| 구분 | 지표 | 종가 | 전일 대비 | 거래량 | RSI(14) | 60일 추세 | 기준일 |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | --- | --- |")
        for title, syms in ctx["sections"]:
            for sym in syms:
                hist = ctx["histories"][sym]
                last, prev = hist[-1], hist[-2]
                chg = (last["close"] - prev["close"]) / prev["close"] * 100 if prev["close"] else 0.0
                vol = f"{last['volume']:,.0f}" if last["volume"] else ""
                rsi = rsi_series([r["close"] for r in hist])[-1]
                rsi_s = f"{rsi:.0f}" if rsi is not None else ""
                spark = charts.sparkline([r["close"] for r in hist[-60:]])
                lines.append(f"| {title} | {ctx['names'][sym]} | {last['close']:,.2f} "
                             f"| {chg:+.2f}% | {vol} | {rsi_s} | {spark} | {last['date']} |")

    fg = ctx.get("fear_greed")
    if fg:
        lines.append(f"\nCNN 공포·탐욕 지수: {fg['score']} ({fg['rating']})")
    return "\n".join(lines)


def collect() -> str:
    """대시보드 + 등록된 모든 시장 신호를 마크다운으로 반환."""
    ctx = collect_context()
    return dashboard_md(ctx) + "\n\n" + signals.run_all(ctx)
