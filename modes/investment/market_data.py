"""시장 데이터 수집 레이어 — API 키 없이 받을 수 있는 무료 소스 사용.

- 일별 시세(종가·거래량): Stooq 히스토리 CSV. 히스토리를 받는 이유:
  ① 등락률을 전일 종가 대비로 정확히 계산, ② 신호 모듈(다이버전스·반등
  품질·RSI 등)에 추세 데이터가 필요.
- 공포·탐욕 지수: CNN Fear & Greed.

신호 판정 자체는 modes/investment/signals/ 패키지가 담당한다.
"""
import csv
import io
import os
from datetime import date, timedelta

import requests

from modes.investment import signals
from modes.investment.indicators import rsi_series

# 기본 워치리스트: (stooq 심볼, 표시 이름)
# .env의 WATCHLIST로 교체 가능. 형식: "심볼:이름,심볼:이름,..."
DEFAULT_WATCHLIST = [
    ("^spx", "S&P 500"),
    ("^ndq", "나스닥 100"),
    ("^dji", "다우존스"),
    ("^sox", "필라델피아 반도체"),
    ("^kospi", "코스피"),
    ("^vix", "VIX"),
    ("usdkrw", "원/달러"),
    ("btcusd", "비트코인 (USD)"),
    ("10usy.b", "미 국채 10년물"),
    ("nvda.us", "엔비디아"),
    ("mu.us", "마이크론"),
]

_UA = {"User-Agent": "Mozilla/5.0 (daily-journal-agent)"}


def watchlist():
    env = os.environ.get("WATCHLIST", "").strip()
    if not env:
        return DEFAULT_WATCHLIST
    items = []
    for part in env.split(","):
        if ":" in part:
            sym, name = part.split(":", 1)
            items.append((sym.strip(), name.strip()))
    return items or DEFAULT_WATCHLIST


def fetch_history(symbol: str, days: int = 120):
    """Stooq에서 일별 시세 히스토리를 받는다 (과거→최신 순). 실패 시 []."""
    d2 = date.today()
    d1 = d2 - timedelta(days=days)
    url = (f"https://stooq.com/q/d/l/?s={symbol}&i=d"
           f"&d1={d1.strftime('%Y%m%d')}&d2={d2.strftime('%Y%m%d')}")
    try:
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
    """워치리스트 히스토리 + 심리 지표를 한 번 수집해 신호 모듈들과 공유."""
    ctx = {"histories": {}, "names": {}}
    for sym, name in watchlist():
        hist = fetch_history(sym)
        if len(hist) >= 2:
            ctx["histories"][sym] = hist
            ctx["names"][sym] = name
    ctx["fear_greed"] = fetch_fear_greed()
    return ctx


def dashboard_md(ctx) -> str:
    """종가·등락률·거래량·RSI 대시보드 표."""
    lines = ["### 오늘의 시장 대시보드"]
    if not ctx["histories"]:
        lines.append("- (시세 데이터 수집 실패)")
    else:
        lines.append("| 지표 | 종가 | 전일 대비 | 거래량 | RSI(14) | 기준일 |")
        lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
        for sym, hist in ctx["histories"].items():
            last, prev = hist[-1], hist[-2]
            chg = (last["close"] - prev["close"]) / prev["close"] * 100 if prev["close"] else 0.0
            vol = f"{last['volume']:,.0f}" if last["volume"] else ""
            rsi = rsi_series([r["close"] for r in hist])[-1]
            rsi_s = f"{rsi:.0f}" if rsi is not None else ""
            lines.append(f"| {ctx['names'][sym]} | {last['close']:,.2f} | {chg:+.2f}% "
                         f"| {vol} | {rsi_s} | {last['date']} |")

    fg = ctx.get("fear_greed")
    if fg:
        lines.append(f"\nCNN 공포·탐욕 지수: {fg['score']} ({fg['rating']})")
    return "\n".join(lines)


def collect() -> str:
    """대시보드 + 등록된 모든 시장 신호를 마크다운으로 반환."""
    ctx = collect_context()
    return dashboard_md(ctx) + "\n\n" + signals.run_all(ctx)
