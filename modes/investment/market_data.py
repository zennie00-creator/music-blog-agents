"""시장 데이터 수집 — API 키 없이 받을 수 있는 무료 소스 사용.

- 지수/환율/코인 시세: Stooq CSV (https://stooq.com) — 키 불필요
- 공포·탐욕 지수: CNN Fear & Greed — 키 불필요 (실패해도 파이프라인은 계속)
"""
import csv
import io

import requests

# (stooq 심볼, 표시 이름)
DEFAULT_SYMBOLS = [
    ("^spx", "S&P 500"),
    ("^ndq", "나스닥 100"),
    ("^dji", "다우존스"),
    ("^kospi", "코스피"),
    ("^vix", "VIX"),
    ("usdkrw", "원/달러"),
    ("btcusd", "비트코인 (USD)"),
    ("10usy.b", "미국 10년물 금리"),
]

_UA = {"User-Agent": "Mozilla/5.0 (daily-journal-agent)"}


def fetch_quotes(symbols=None):
    """Stooq에서 종가·등락률을 가져온다. 실패한 심볼은 건너뛴다."""
    symbols = symbols or DEFAULT_SYMBOLS
    sym_param = ",".join(s for s, _ in symbols)
    url = f"https://stooq.com/q/l/?s={sym_param}&f=sd2t2ohlcv&h&e=csv"
    quotes = []
    try:
        r = requests.get(url, headers=_UA, timeout=30)
        r.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(r.text)))
    except Exception as e:
        print(f"  ⚠️ 시세 수집 실패: {e}")
        return quotes

    names = {s.upper(): n for s, n in symbols}
    for row in rows:
        try:
            close = float(row["Close"])
            open_ = float(row["Open"])
        except (KeyError, ValueError, TypeError):
            continue  # N/D (데이터 없음)
        change_pct = (close - open_) / open_ * 100 if open_ else 0.0
        quotes.append({
            "name": names.get(row["Symbol"].upper(), row["Symbol"]),
            "symbol": row["Symbol"],
            "date": row.get("Date", ""),
            "close": close,
            "change_pct": round(change_pct, 2),
        })
    return quotes


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


def collect() -> str:
    """전체 시장 데이터를 수집해 마크다운 텍스트로 반환."""
    lines = ["### 오늘의 시장 데이터"]
    quotes = fetch_quotes()
    if quotes:
        for q in quotes:
            arrow = "🔺" if q["change_pct"] > 0 else ("🔻" if q["change_pct"] < 0 else "➖")
            lines.append(f"- {q['name']}: {q['close']:,.2f} ({arrow} 당일 {q['change_pct']:+.2f}%) [{q['date']}]")
    else:
        lines.append("- (시세 데이터 수집 실패)")

    fg = fetch_fear_greed()
    if fg:
        lines.append(f"- CNN 공포·탐욕 지수: {fg['score']} ({fg['rating']})")

    return "\n".join(lines)
