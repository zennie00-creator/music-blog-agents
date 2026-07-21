"""구글시트(웹 게시 CSV) 시세 소스 — Yahoo 429(Actions IP 차단) 우회.

구글이 자기 서버에서 GOOGLEFINANCE 수식을 실시간 계산해 CSV로 내려주므로,
GitHub Actions의 데이터센터 IP에서도 IP 차단 없이 미국 지수·종목 시세를 받는다.

게시 CSV 형식 (헤더 없음, 한 줄 = 한 종목):
    티커, 현재가, 전일비(%), 거래량
    INDEXSP:.INX, 7443.28, -0.19, 2726531038
    NASDAQ:NVDA,  203.28,   0.23, 0

한계: 이력이 아니라 '오늘 스냅숏'이다. 그래서
  ① 매일 스냅숏을 market_history/gsheet.jsonl에 누적 → 시간이 지나며 신호용
     이력(RSI·추세·다이버전스)이 채워진다 (Actions가 커밋해 보존).
  ② 이력이 2개 미만인 날엔 전일비(%)로 '어제 종가'를 역산해 2점짜리 시계열을
     즉석에서 만들어 대시보드 등락률을 첫날부터 정확히 보여준다.

설정: 환경변수 MARKET_CSV_URLS (쉼표로 여러 URL 가능). 미설정 시 비활성(빈 dict).
"""
import csv
import io
import json
import os
import re
import urllib.parse
from datetime import date as _date, timedelta

import requests

from core import config

_UA = {"User-Agent": "Mozilla/5.0 (compatible; invest-bot/1.0)"}
LOG_DIR = os.path.join(config.ROOT_DIR, "market_history")
_STORE = os.path.join(LOG_DIR, "gsheet.jsonl")

# 티커 판별: 대문자·숫자·`:._-` 로 구성되고 최소 한 글자는 A-Z (헤더/한글/빈칸 제외)
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.:_-]*$")

# 프로세스 내 캐시 (매 심볼마다 재조회 방지)
_SNAPSHOT = None   # {ticker: {"price","changepct","volume"}}
_HISTORY = None    # {ticker: [ {date, close, volume} ... ]}  (누적 저장분)


def _urls():
    raw = (config.MARKET_CSV_URLS or "").strip()
    return [u.strip() for u in raw.split(",") if u.strip()]


def _num(s):
    """CSV 셀 → float. '#N/A'·''·'Loading...'·콤마 등은 None(거래량은 0)."""
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if not s or s.startswith("#") or not re.match(r"^-?\d", s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# CBOE 금리지수는 GOOGLEFINANCE가 금리×10으로 준다(TNX 45.4 = 4.54%).
# 시트에서 이미 ÷10 했으면 값이 ≤15라 건드리지 않음(자동 적응).
_CBOE_YIELD = {"INDEXCBOE:IRX", "INDEXCBOE:FVX", "INDEXCBOE:TNX", "INDEXCBOE:TYX"}


def _norm_price(ticker: str, price):
    if ticker in _CBOE_YIELD and price is not None and price > 15:
        return price / 10
    return price


def _is_ticker(cell: str) -> bool:
    """티커 셀 판별: 티커 패턴 + 최소 한 글자는 A-Z (빈칸·숫자·한글 제외)."""
    return bool(_TICKER_RE.match(cell)) and any(c.isalpha() for c in cell)


def parse_market_csv(text: str) -> dict:
    """게시 CSV 텍스트 → {티커: {price, changepct, volume}}.

    티커 열을 자동 탐지한다 — 시트 앞에 빈 열이나 종목명 열이 있어도
    (예: ',INDEXSP:.INX,7443.28,...') 티커 패턴인 첫 셀부터 읽는다.
    헤더·깨진 줄은 건너뜀.
    """
    out = {}
    for row in csv.reader(io.StringIO(text)):
        cells = [c.strip() for c in row]
        ti = next((i for i, c in enumerate(cells) if _is_ticker(c)), None)
        if ti is None:
            continue  # 티커 없는 줄(헤더·빈줄·종목명만)
        price = _num(cells[ti + 1]) if len(cells) > ti + 1 else None
        if price is None:
            continue
        out[cells[ti]] = {
            "price": _norm_price(cells[ti], price),
            "changepct": _num(cells[ti + 2]) if len(cells) > ti + 2 else None,
            "volume": (_num(cells[ti + 3]) if len(cells) > ti + 3 else None) or 0.0,
        }
    return out


def fetch_snapshot() -> dict:
    """설정된 CSV URL(들)을 받아 합친 스냅숏. 미설정/실패 시 부분/빈 dict.

    미국 시세가 왜 안 들어오는지 로그로 바로 진단되게 각 단계를 출력한다.
    """
    urls = _urls()
    print(f"  🔗 MARKET_CSV_URLS: {len(urls)}개 URL")
    snap = {}
    for url in urls:
        try:
            r = requests.get(url, headers=_UA, timeout=30)
            print(f"    · GET {url[:55]}… → HTTP {r.status_code}, {len(r.text)}바이트")
            r.raise_for_status()
            parsed = parse_market_csv(r.text)
            if parsed:
                snap.update(parsed)
            else:
                head = r.text[:150].replace("\n", "⏎")
                print(f"    ⚠️ 0종목 파싱됨 — CSV가 아닐 수 있음. 응답 앞부분: {head!r}")
        except Exception as e:
            print(f"    ⚠️ 수집 실패: {e}")
    return snap


def _load_store():
    """market_history/gsheet.jsonl → {ticker: [{date,close,volume}...]} (날짜순)."""
    hist = {}
    if not os.path.exists(_STORE):
        return hist
    with open(_STORE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = rec.get("date")
            for tk, cv in rec.get("prices", {}).items():
                close = cv[0] if isinstance(cv, list) else cv
                vol = cv[1] if isinstance(cv, list) and len(cv) > 1 else 0.0
                if close is not None:
                    hist.setdefault(tk, []).append({"date": d, "close": float(close),
                                                    "volume": float(vol or 0.0)})
    for rows in hist.values():
        rows.sort(key=lambda r: r["date"])
    return hist


def _save_today(snapshot: dict, today: str):
    """오늘 스냅숏을 저장소에 기록 (같은 날짜는 덮어씀)."""
    if not snapshot:
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    lines = []
    if os.path.exists(_STORE):
        with open(_STORE, encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines()
                     if ln.strip() and json.loads(ln).get("date") != today]
    prices = {tk: [v["price"], v.get("volume") or 0.0] for tk, v in snapshot.items()}
    lines.append(json.dumps({"date": today, "prices": prices}, ensure_ascii=False))
    with open(_STORE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def refresh(today: str = ""):
    """스냅숏 1회 수집 + 저장소 갱신 + 캐시 적재. collect_context 시작 시 호출."""
    global _SNAPSHOT, _HISTORY
    today = today or _date.today().isoformat()
    _SNAPSHOT = fetch_snapshot()
    if _SNAPSHOT:
        _save_today(_SNAPSHOT, today)
        print(f"  🧮 구글시트 시세 {len(_SNAPSHOT)}종목 수집 (이력 누적)")
    _HISTORY = _load_store()
    return _SNAPSHOT


# 구글 티커 → Yahoo 심볼 (백필용). 미국 주식은 거래소 접두사만 떼면 됨.
_YAHOO_MAP = {
    "INDEXSP:.INX": "^GSPC", "INDEXNASDAQ:NDX": "^NDX", "INDEXDJX:.DJI": "^DJI",
    "INDEXNASDAQ:SOX": "^SOX", "INDEXCBOE:VIX": "^VIX", "KRX:KOSPI": "^KS11",
    "INDEXCBOE:IRX": "^IRX", "INDEXCBOE:FVX": "^FVX", "INDEXCBOE:TNX": "^TNX",
    "INDEXCBOE:TYX": "^TYX", "INDEXHANGSENG:HSI": "^HSI", "CURRENCY:USDKRW": "KRW=X",
}


def _to_yahoo(ticker: str):
    if ticker in _YAHOO_MAP:
        return _YAHOO_MAP[ticker]
    # NASDAQ:NVDA / NYSE:COHR → NVDA / COHR ; 접두사 없는 PLTR → PLTR
    if ":" in ticker:
        exch, sym = ticker.split(":", 1)
        return sym if exch in ("NASDAQ", "NYSE", "NYSEARCA", "BATS", "AMEX") else None
    return ticker


# 구글 티커 → stooq 심볼. stooq CSV는 Actions IP에서도 되는 경우가 많아 우선 시도.
_STOOQ_MAP = {
    "INDEXSP:.INX": "^spx", "INDEXNASDAQ:NDX": "^ndx", "INDEXDJX:.DJI": "^dji",
    "INDEXNASDAQ:SOX": "^sox", "INDEXCBOE:VIX": "^vix", "KRX:KOSPI": "^kospi",
}


def _to_stooq(ticker: str):
    if ticker in _STOOQ_MAP:
        return _STOOQ_MAP[ticker]
    if ticker.startswith("INDEXCBOE:") or ticker.startswith("CURRENCY:"):
        return None  # 금리·환율은 stooq 매핑 생략 (시트 일봉으로 충분)
    if ":" in ticker:
        exch, sym = ticker.split(":", 1)
        return sym.lower() + ".us" if exch in ("NASDAQ", "NYSE", "NYSEARCA", "BATS", "AMEX") else None
    return ticker.lower() + ".us"  # PLTR → pltr.us


def _fetch_stooq(stooq_sym: str, days: int):
    """stooq 일봉 CSV → [{date, close, volume}] (과거→최신). 헤더: Date,Open,High,Low,Close,Volume."""
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(stooq_sym)}&i=d"
    r = requests.get(url, headers=_UA, timeout=20)
    r.raise_for_status()
    text = r.text.strip()
    if not text or text.lower().startswith("<") or "no data" in text.lower():
        raise ValueError("stooq 데이터 없음/차단")
    rows = []
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    for row in reader:
        if len(row) < 5:
            continue
        try:
            rows.append({"date": row[0], "close": float(row[4]),
                         "volume": float(row[5]) if len(row) > 5 and row[5] not in ("", "N/A") else 0.0})
        except ValueError:
            continue
    return rows[-days:] if days else rows


def _read_by_date():
    by_date = {}
    if os.path.exists(_STORE):
        with open(_STORE, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                by_date.setdefault(rec["date"], {}).update(rec.get("prices", {}))
    return by_date


def _write_by_date(by_date):
    os.makedirs(LOG_DIR, exist_ok=True)
    lines = [json.dumps({"date": d, "prices": by_date[d]}, ensure_ascii=False)
             for d in sorted(by_date)]
    with open(_STORE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _backfill_one(tk: str, days: int):
    """한 티커의 과거 이력을 stooq(우선)→Yahoo 순으로 시도. (rows, 소스명) 반환."""
    from modes.investment import market_data
    ssym = _to_stooq(tk)
    if ssym:
        try:
            rows = _fetch_stooq(ssym, days)
            if len(rows) >= 5:
                return rows, f"stooq:{ssym}"
        except Exception as e:
            print(f"    · stooq {ssym} 실패 → Yahoo 시도: {e}")
    ysym = _to_yahoo(tk)
    if ysym:
        try:
            return market_data._fetch_yahoo(ysym, days), f"yahoo:{ysym}"
        except Exception as e:
            print(f"    · yahoo {ysym} 실패: {e}")
    return [], ""


def backfill_history(days: int = 200):
    """gsheet/ 티커 과거 이력 백필 — stooq(Actions에서도 됨) 우선, 실패 시 Yahoo(로컬).

    브라우저에서 Actions `backfill` 모드로 돌리면 맥 없이도 stooq로 채워진다.
    기존 날짜·티커는 보존(오늘 실측 유지), 빈 곳만 채운다. 거래량도 함께.
    """
    from modes.investment import portfolio
    sections, _ = portfolio.load()
    tickers = [s.split("/", 1)[1] for _, items in sections for s, _ in items
               if s.startswith("gsheet/")]
    by_date = _read_by_date()
    ok = 0
    for tk in tickers:
        rows, src = _backfill_one(tk, days)
        if not rows:
            print(f"  ⏭ {tk}: 백필 소스 없음")
            continue
        for r in rows:
            close = _norm_price(tk, r["close"])
            by_date.setdefault(r["date"], {}).setdefault(
                tk, [close, r.get("volume") or 0.0])
        ok += 1
        print(f"  ✅ {tk} ({src}): {len(rows)}일")
    _write_by_date(by_date)
    print(f"\n백필 완료: {ok}/{len(tickers)}종목 → {_STORE}")


# 하위호환 별칭 (기존 --backfill 경로)
def backfill_from_yahoo(days: int = 200):
    backfill_history(days)


def history_for(ticker: str):
    """누적 이력 반환. 2점 미만이면 전일비(%)로 어제 종가를 역산해 보강."""
    if _HISTORY is None:
        refresh()
    rows = list(_HISTORY.get(ticker, []))
    if len(rows) >= 2:
        return rows

    snap = (_SNAPSHOT or {}).get(ticker)
    if not snap:
        return rows
    today = rows[-1]["date"] if rows else _date.today().isoformat()
    price = snap["price"]
    vol = snap.get("volume") or 0.0
    chg = snap.get("changepct")
    # 전일비(%)가 있으면 어제 종가를 역산, 없으면(#N/A 등) 평행(=오늘값)으로 둔다.
    # 어느 경우든 2점을 만들어 첫날부터 대시보드에 표시되게 한다 (금리 등).
    if chg is not None and (1 + chg / 100) != 0:
        prev_close = round(price / (1 + chg / 100), 4)
    else:
        prev_close = price
    try:
        y = (_date.fromisoformat(today) - timedelta(days=1)).isoformat()
    except ValueError:
        y = today + "-prev"
    return [{"date": y, "close": prev_close, "volume": 0.0},
            {"date": today, "close": price, "volume": vol}]
