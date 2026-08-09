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


def csv_text(r) -> str:
    """응답 본문을 UTF-8로 읽는다.

    requests는 Content-Type에 charset이 없으면 text/*를 ISO-8859-1로 디코딩한다
    (RFC 2616). 구글 게시 CSV는 UTF-8인데 charset을 안 붙일 때가 있어, 한글 헤더
    '종목명,현재가,티커'가 'ì¢ëª©ëª,í˜„ìž¬ê°€,티커'류로 깨진다. 그러면 헤더 인식이
    실패하고 위치 규칙으로 폴백해 전일비를 가격으로 저장한다 — 2026-08-09에
    실제로 그렇게 이력이 오염됐다. 티커는 ASCII라 멀쩡히 살아남기 때문에
    '그럴듯하게 잘못된' 결과가 나와 눈으로는 발견되지 않는다."""
    return r.content.decode("utf-8", errors="replace")


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


# CBOE 금리지수는 GOOGLEFINANCE가 금리×10으로 준다(TNX 46.6 = 4.66%). 항상 ÷10 한다.
#
# 예전에는 '값이 15보다 클 때만' 나눴다. 시트에서 이미 ÷10 한 경우를 자동으로
# 넘기려는 의도였지만, 금리가 1.5% 밑으로 가면 지수값이 15 이하가 되어 보정이
# 걸리지 않는다 — 1.4%가 14%로 기록된다. 2020~21년 3개월물은 0.05% 수준이었으니
# 가상의 위험이 아니고, 하필 완화 사이클(금리 커브가 가장 중요한 국면)에 터진다.
# GOOGLEFINANCE는 항상 ×10을 주므로 조건 없이 나누는 쪽이 안전하다.
# → 시트에서는 ÷10 하지 말 것. 원본 그대로 두면 된다.
_CBOE_YIELD = {"INDEXCBOE:IRX", "INDEXCBOE:FVX", "INDEXCBOE:TNX", "INDEXCBOE:TYX"}
_YIELD_SANE_MAX = 20.0     # 미 국채가 이 이상이면 소스나 배치가 잘못된 것


def _norm_price(ticker: str, price):
    if ticker not in _CBOE_YIELD or price is None:
        return price
    y = price / 10
    if y > _YIELD_SANE_MAX:
        # 시트가 이미 나눈 값을 또 나누면 반대로 10배 작아진다. 어느 쪽이든
        # 조용히 넘기지 않고 알린다 — 커브 신호가 통째로 틀어지는 값이다.
        print(f"  ⚠️ {ticker} 금리 {y:.2f}% — 비정상. 시트에서 ÷10 하고 있지 않은지 확인")
    return y


def _is_ticker(cell: str) -> bool:
    """티커 셀 판별: 티커 패턴 + 최소 한 글자는 A-Z (빈칸·숫자·한글 제외)."""
    return bool(_TICKER_RE.match(cell)) and any(c.isalpha() for c in cell)


# 헤더 이름 → 의미. 시트마다 열 순서가 다를 수 있어 1행 헤더가 있으면 그걸 따른다.
_HEADER_KEYS = {
    "ticker": ("티커", "심볼", "종목코드", "ticker", "symbol", "code"),
    "price": ("현재가", "종가", "가격", "price", "close", "last"),
    "changepct": ("전일비", "등락", "변동", "change", "chg", "pct"),
    "volume": ("거래량", "volume", "vol"),
}


def _header_map(cells):
    """헤더 행이면 {의미: 열번호}, 아니면 None.

    티커 열 위치를 이름으로 알아내면 '티커 오른쪽이 현재가'라는 위치 가정을 안 써도
    된다. 실제로 시트가 (종목명, 현재가, 티커, 전일비) 순인 경우가 있는데, 위치로만
    읽으면 전일비를 현재가로 집어 조용히 틀린 값이 들어간다 — 둘 다 숫자라
    값만 봐서는 구분이 불가능하다."""
    mapping = {}
    for i, c in enumerate(cells):
        low = c.strip().lower()
        if not low:
            continue
        for role, names in _HEADER_KEYS.items():
            if role in mapping:
                continue
            if any(n in low for n in names):
                mapping[role] = i
                break
    # 티커와 현재가를 모두 짚어내야 신뢰할 수 있는 헤더다
    return mapping if "ticker" in mapping and "price" in mapping else None


def parse_market_csv(text: str) -> dict:
    """게시 CSV 텍스트 → {티커: {price, changepct, volume}}.

    1행에 헤더(티커·현재가…)가 있으면 열 순서를 그대로 따르고, 없으면 기존처럼
    '티커 패턴인 첫 셀 + 오른쪽 3칸' 위치 규칙으로 읽는다. 헤더가 있는 시트는
    열을 어떻게 배치해도 정확히 읽히고, 헤더가 없던 기존 시트는 동작이 안 바뀐다.
    """
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text))]
    rows = [r for r in rows if any(r)]        # 빈 줄 제거
    if not rows:
        return {}

    header, start = None, 0
    if not any(_is_ticker(c) for c in rows[0]):
        # 첫 줄에 티커가 없다 = 헤더 행이다. 헤더가 있는 시트는 열 배치가
        # 위치 규칙과 다를 수 있으므로, 헤더를 못 읽으면 추측하지 않고 포기한다.
        # 추측했다가 실제로 전일비를 가격으로 저장한 적이 있다(2026-08-09):
        # S&P 7757.64 → 0.62, 종목명이 대문자인 행은 종목명이 티커로 들어갔다.
        header = _header_map(rows[0])
        start = 1
        if header is None:
            print("  ⚠️ 첫 줄을 헤더로 읽지 못했습니다 — 열 이름을 확인하세요. "
                  f"실제 첫 줄: {rows[0][:6]}")
            return {}

    out = {}
    for cells in rows[start:]:
        if header:
            # 헤더가 있으면 티커도 지정된 열에서 읽는다. '첫 티커 같은 셀'을 찾으면
            # 종목명이 대문자인 줄(IRX, SPCX 등)에서 종목명을 티커로 집는다.
            i = header["ticker"]
            ti = i if i < len(cells) and _is_ticker(cells[i]) else None
        else:
            ti = next((i for i, c in enumerate(cells) if _is_ticker(c)), None)
        if ti is None:
            continue  # 헤더·빈줄·티커 없는 줄

        def at(role, fallback_offset):
            """헤더가 있으면 지정된 열, 없으면 티커 기준 상대 위치."""
            i = header.get(role) if header else None
            if i is None:
                i = ti + fallback_offset
            return _num(cells[i]) if 0 <= i < len(cells) else None

        price = at("price", 1)
        if price is None:
            continue
        out[cells[ti]] = {
            "price": _norm_price(cells[ti], price),
            "changepct": at("changepct", 2),
            "volume": at("volume", 3) or 0.0,
        }
    return out


# 시트로는 못 받지만 러너에서는 직접 뚫리는 지표. 스냅숏에 끼워 넣으면 기존
# 누적·이력 경로를 그대로 타므로 별도 저장 장치가 필요 없다.
#   금: GOOGLEFINANCE가 귀금속을 지원하지 않고(CURRENCY:XAUUSD → #N/A) 시트의
#   IMPORTDATA는 stooq·네이버에 막혔다. gold-api는 --check 프로브에서 러너 HTTP 200
#   확인됨(2026-08-08). 온스당 현물($/oz)이며 COMEX 최근월물과는 베이시스만큼 차이.
_DIRECT_SOURCES = [("XAUUSD", "https://api.gold-api.com/price/XAU")]


def _fetch_direct() -> dict:
    """시트 밖에서 직접 받는 지표 → parse_market_csv와 같은 형식. 실패분은 건너뜀.

    응답 구조가 제공자마다 달라 키 이름을 가정하지 않는다. 'price'가 들어간 키의
    숫자 중 상식적인 범위의 값을 집는다(Put/Call 파서와 같은 방식)."""
    out = {}
    for ticker, url in _DIRECT_SOURCES:
        try:
            r = requests.get(url, headers=_UA, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"    · 직접 수집 실패 {ticker}: {type(e).__name__} {str(e)[:60]}")
            continue
        found = []          # [(키, 값)] — 'price'가 들어간 키의 숫자 전부

        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool) \
                            and "price" in str(k).lower() and 0 < v < 1e7:
                        found.append((str(k).lower(), float(v)))
                    else:
                        walk(v)
            elif isinstance(o, list):
                for item in o:
                    walk(item)

        walk(data)
        # 한 응답에 여러 자산이 실려 있을 수 있다(예: xauPrice와 xagPrice가 나란히).
        # 티커의 자산코드가 키에 들어간 것을 우선하고, 없으면 정확히 'price'인 것,
        # 그것도 없으면 첫 번째를 쓴다. 순서만 보고 고르면 은값을 금값으로 집는다.
        code = ticker[:3].lower()
        price = next((v for k, v in found if code in k),
                     next((v for k, v in found if k == "price"),
                          found[0][1] if found else None))
        if price is None:
            print(f"    · 직접 수집 {ticker}: 응답에서 가격을 못 찾음 "
                  f"(후보 {len(found)}개)")
            continue
        out[ticker] = {"price": price, "changepct": None, "volume": 0.0}
        print(f"    · 직접 수집 {ticker}: {price}")
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
            body = csv_text(r)
            print(f"    · GET {url[:55]}… → HTTP {r.status_code}, {len(body)}자")
            r.raise_for_status()
            parsed = parse_market_csv(body)
            if parsed:
                snap.update(parsed)
            else:
                head = body[:150].replace("\n", "⏎")
                print(f"    ⚠️ 0종목 파싱됨 — CSV가 아닐 수 있음. 응답 앞부분: {head!r}")
        except Exception as e:
            print(f"    ⚠️ 수집 실패: {e}")
    # 시트에 없는 지표를 직접 채운다. 시트 값이 있으면 그쪽을 존중한다 —
    # 나중에 시트에 추가하면 별도 조치 없이 시트가 우선이 된다.
    for tk, v in _fetch_direct().items():
        snap.setdefault(tk, v)
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


_SANITY_MOVE = 0.5      # 하루 ±50%를 넘는 변동
_SANITY_SHARE = 0.3     # 이 비율 넘는 종목이 그러면 파싱이 어긋난 것으로 본다


def _plausible(snapshot: dict, prior_close: dict) -> bool:
    """스냅숏이 직전 종가 대비 상식적인지. 어긋나면 False.

    열을 잘못 집으면 값이 전부 그럴듯하게 '작은 숫자'가 된다 — 실제로 전일비를
    가격으로 저장해 S&P가 7757.64에서 0.62가 된 적이 있다(2026-08-09). 개별 종목의
    큰 변동은 있을 수 있지만 여러 종목이 동시에 반토막 나는 일은 파싱 오류뿐이다."""
    checked = [(tk, v["price"], prior_close[tk]) for tk, v in snapshot.items()
               if tk in prior_close and prior_close[tk]]
    if len(checked) < 5:
        return True                      # 비교 대상이 적으면 판단하지 않는다
    odd = [(tk, c, pc) for tk, c, pc in checked
           if abs(c / float(pc) - 1) > _SANITY_MOVE]
    if len(odd) / len(checked) <= _SANITY_SHARE:
        return True
    print(f"  🚨 스냅숏 저장 취소 — {len(odd)}/{len(checked)}종목이 직전 종가 대비 "
          f"±{_SANITY_MOVE:.0%}를 넘습니다. 열 배치가 어긋났을 가능성이 큽니다.")
    for tk, c, pc in odd[:4]:
        print(f"     · {tk}: {pc} → {c}")
    return False


def _save_today(snapshot: dict, today: str):
    """오늘 스냅숏을 저장소에 기록 (같은 날짜는 덮어씀).

    시트의 '현재가'는 장 마감 전이면 직전 미국 장 종가와 같다. 그 값을 오늘로
    또 저장하면 백필된 직전일과 종가가 중복돼 전일 대비가 0%가 된다. 그래서
    직전 저장 종가와 같은 종목은 오늘 기록에서 제외한다(새 정보 없음)."""
    if not snapshot:
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    lines, existing = [], {}
    if os.path.exists(_STORE):
        with open(_STORE, encoding="utf-8") as f:
            for ln in f.read().splitlines():
                if not ln.strip():
                    continue
                rec = json.loads(ln)
                if rec.get("date") == today:
                    continue  # 오늘 라인은 재작성
                lines.append(ln)
                existing[rec["date"]] = rec.get("prices", {})
    prior_close = {}  # 티커별 '오늘 이전 최신' 종가
    for d in sorted(existing):
        for tk, cv in existing[d].items():
            prior_close[tk] = cv[0] if isinstance(cv, list) else cv
    if not _plausible(snapshot, prior_close):
        return                    # 통째로 어긋난 스냅숏 — 좋은 이력을 덮지 않는다
    prices = {}
    for tk, v in snapshot.items():
        c = v["price"]
        pc = prior_close.get(tk)
        if pc is not None and round(float(pc), 4) == round(float(c), 4):
            continue  # 직전 종가와 동일 → 같은 세션, 중복 저장 안 함
        prices[tk] = [c, v.get("volume") or 0.0]
    if prices:  # 전부 중복이면 오늘 라인은 만들지 않음
        lines.append(json.dumps({"date": today, "prices": prices}, ensure_ascii=False))
    with open(_STORE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def reconcile_recent_volumes(lookback: int = 10):
    """최근 며칠치 저장 거래량을 마감 후 네이버 실측으로 보정한다.

    구글시트가 주는 '당일' 거래량은 장중엔 미확정이라 개별주는 0, 지수는 원주(raw)라
    백필(네이버=千 단위)과 스케일이 어긋난다. 그래서 거래량의 신뢰 소스를 백필과
    같은 네이버로 통일한다: 매일 실행 시 최근 lookback일 중 네이버에 마감 거래량이
    있는 날짜만 그 값으로 덮어쓴다. 종가는 건드리지 않는다(거래량 cv[1]만).

    · 당일(장중·미마감)은 네이버에도 아직 없어 0으로 남는다 → 차트에선 갭.
    · 그 다음날 = 네이버에 마감 거래량이 들어오면 자동으로 채워진다.
    """
    from modes.investment import portfolio
    sections, _ = portfolio.load()
    tickers = [s.split("/", 1)[1] for _, items in sections for s, _ in items
               if s.startswith("gsheet/")]
    by_date = _read_by_date()
    recent = sorted(by_date)[-lookback:]
    if not recent:
        return
    recent_set = set(recent)
    filled = 0
    for tk in tickers:
        codes = _naver_codes(tk)  # 거래량 없는 티커(환율·금리 등)는 [] → 건너뜀
        if not codes:
            continue
        rows = []
        for nc in codes:
            try:
                rows = _fetch_naver_world(nc, lookback + 5)
                if rows:
                    break
            except Exception:
                continue  # 조용히 스킵 — 브리프 본류를 막지 않는다
        if not rows:
            continue
        vol_by_date = {r["date"]: (r.get("volume") or 0.0) for r in rows}
        for d in recent_set:
            cv = by_date[d].get(tk)
            if not (isinstance(cv, list) and len(cv) > 1):
                continue
            v = vol_by_date.get(d)
            if v and round(float(v), 2) != round(float(cv[1] or 0), 2):
                cv[1] = float(v)  # 네이버 마감 실측으로 덮어씀 (종가 cv[0]은 유지)
                filled += 1
    if filled:
        _write_by_date(by_date)
        print(f"  🔁 거래량 보정: {filled}건 (최근 {lookback}일, 네이버 마감 실측)")


def refresh(today: str = ""):
    """스냅숏 1회 수집 + 저장소 갱신 + 캐시 적재. collect_context 시작 시 호출."""
    global _SNAPSHOT, _HISTORY
    today = today or _date.today().isoformat()
    _SNAPSHOT = fetch_snapshot()
    if _SNAPSHOT:
        _save_today(_SNAPSHOT, today)
        print(f"  🧮 구글시트 시세 {len(_SNAPSHOT)}종목 수집 (이력 누적)")
    try:
        reconcile_recent_volumes()  # 전날치 거래량을 네이버 마감값으로 보정
    except Exception as e:
        print(f"  ⚠️ 거래량 보정 스킵: {e}")
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


def _sheet_date(cell: str):
    """GOOGLEFINANCE 날짜 셀 → 'YYYY-MM-DD'. 못 읽으면 None.

    게시 CSV의 날짜 형식은 시트 로케일을 탄다(한국어면 '2019. 1. 2', 영어면
    '1/2/2019'). TEXT()로 감싸 ISO로 내리는 걸 권하지만, 안 감싼 시트도 받아준다."""
    s = (cell or "").strip()
    if not s:
        return None
    s = s.split(" ")[0] if "-" in s.split(" ")[0] else s   # '2019-01-02 00:00:00'
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
    else:
        # '2019. 1. 2' (한국어 로케일)
        m = re.match(r"^(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", s)
        if m:
            y, mo, d = m.groups()
        else:
            # '1/2/2019' — GOOGLEFINANCE 영어 로케일은 M/D/YYYY
            m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
            if not m:
                return None
            mo, d, y = m.groups()
    try:
        return _date(int(y), int(mo), int(d)).isoformat()
    except ValueError:
        return None


def parse_history_csv(text: str) -> dict:
    """이력 탭 게시 CSV → {티커: [{date, close, volume}]}.

    배치: 티커 하나가 2열을 쓴다. 1행에 티커명을 적고, 2행부터 아래로
    GOOGLEFINANCE 기간 조회 결과(날짜, 종가)가 펼쳐진다.

        A1: INDEXCBOE:TNX          C1: NYSEARCA:USO
        A2: =GOOGLEFINANCE(...)    C2: =GOOGLEFINANCE(...)

    GOOGLEFINANCE가 스스로 내는 헤더행('Date','Close')은 날짜로 안 읽히므로
    자연히 걸러진다. 거래량은 이 경로로 오지 않아 0으로 둔다 — 시세·커브 신호는
    살아나고, 거래량이 필요한 신호(다이버전스·반등품질)는 원래대로 스냅숏 누적분을
    쓴다."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    header = rows[0]
    out = {}
    for col, cell in enumerate(header):
        tk = (cell or "").strip()
        if not _is_ticker(tk):
            continue
        series = {}
        for r in rows[1:]:
            if len(r) <= col + 1:
                continue
            day = _sheet_date(r[col])
            close = _num(r[col + 1])
            if day and close is not None:
                series[day] = _norm_price(tk, close)
        if series:
            out[tk] = [{"date": d, "close": series[d], "volume": 0.0}
                       for d in sorted(series)]
    return out


def fetch_sheet_history() -> dict:
    """MARKET_HISTORY_CSV_URLS의 이력 탭들을 받아 합친다. 미설정·실패 시 {}."""
    raw = (config.MARKET_HISTORY_CSV_URLS or "").strip()
    urls = [u.strip() for u in raw.split(",") if u.strip()]
    if not urls:
        return {}
    merged = {}
    for url in urls:
        try:
            r = requests.get(url, headers=_UA, timeout=30)
            r.raise_for_status()
            got = parse_history_csv(csv_text(r))
        except Exception as e:
            print(f"    · 이력 시트 실패 {url[:50]}…: {type(e).__name__} {str(e)[:60]}")
            continue
        print(f"    · 이력 시트 {url[:50]}… → {len(got)}종목")
        for tk, rows in got.items():
            merged.setdefault(tk, rows)
    return merged


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


# 구글 티커 → 네이버 해외주식 로이터코드. 네이버는 Actions IP에서도 되는 게 강점.
_NAVER_WORLD_MAP = {
    "INDEXSP:.INX": ".INX", "INDEXNASDAQ:NDX": ".NDX", "INDEXDJX:.DJI": ".DJI",
    "INDEXNASDAQ:SOX": ".SOX", "INDEXCBOE:VIX": ".VIX",
}


def _to_naver_world(ticker: str):
    if ticker in _NAVER_WORLD_MAP:
        return _NAVER_WORLD_MAP[ticker]
    if ticker == "KRX:KOSPI":
        return "KOSPI"   # 네이버 국내지수 (domestic/index 경로에서 처리)
    if ticker == "KRX:KOSDAQ":
        return "KOSDAQ"
    if ticker.startswith(("INDEX", "CURRENCY", "KRX")):
        return None  # 환율/기타 지수는 매핑 불확실 → 생략
    if ":" in ticker:
        exch, sym = ticker.split(":", 1)
        if exch == "NASDAQ":
            return sym + ".O"
        if exch == "NYSE":
            return sym + ".N"
        return None
    return ticker + ".O"  # 접두사 없는 것(PLTR 등)은 NASDAQ(.O) 가정


def _parse_naver_world(data):
    items = data if isinstance(data, list) else (
        data.get("priceInfos") or data.get("chart") or data.get("result")
        or data.get("dataList") or []) if isinstance(data, dict) else []
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        d = it.get("localDate") or it.get("dt") or it.get("localDateTime") or it.get("date")
        c = it.get("closePrice") or it.get("ncv") or it.get("close") or it.get("clpr")
        v = it.get("accumulatedTradingVolume") or it.get("acml_vol") or it.get("volume") or 0
        if not d or c in (None, ""):
            continue
        ds = str(d)
        date_s = f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}" if len(ds) >= 8 and ds[:8].isdigit() else ds[:10]
        try:
            rows.append({"date": date_s, "close": float(str(c).replace(",", "")),
                         "volume": float(str(v).replace(",", "") or 0)})
        except ValueError:
            continue
    rows.sort(key=lambda x: x["date"])
    return rows


def _fetch_naver_world(code: str, days: int):
    """네이버 해외 일봉. 종목은 /item/, 지수는 /index/ 경로 → 둘 다 시도. 0행이면 원문 노출."""
    end = _date.today()
    start = end - timedelta(days=int(days * 1.6) + 10)
    qs = f"?startDateTime={start:%Y%m%d}0000&endDateTime={end:%Y%m%d}2359"
    last = "?"
    # 종목=foreign/item, 해외지수=foreign/index, 국내지수(KOSPI 등)=domestic/index
    paths = [("foreign", "item"), ("foreign", "index"), ("domestic", "index")]
    for market, kind in paths:
        url = f"https://api.stock.naver.com/chart/{market}/{kind}/{urllib.parse.quote(code)}/day{qs}"
        try:
            r = requests.get(url, headers={**_UA, "Referer": "https://m.stock.naver.com/"}, timeout=15)
            r.raise_for_status()
            rows = _parse_naver_world(r.json())
            if rows:
                return rows[-days:] if days else rows
            last = f"{kind}={str(r.json())[:70]}"
        except requests.HTTPError as e:
            last = f"{kind}=HTTP{e.response.status_code if e.response is not None else '?'}"
    raise ValueError(f"네이버 0행 ({last})")


def _naver_codes(tk: str):
    """네이버 후보 코드 리스트. NYSE는 .N 실패 대비 .O도 시도."""
    base = _to_naver_world(tk)
    if not base:
        return []
    if base.endswith(".N"):
        return [base, base[:-2] + ".O"]
    return [base]


def _backfill_one(tk: str, days: int):
    """한 티커 이력을 네이버(Actions OK)→stooq→Yahoo 순으로 시도. (rows, 소스명)."""
    from modes.investment import market_data
    for nc in _naver_codes(tk):
        try:
            rows = _fetch_naver_world(nc, days)
            if len(rows) >= 5:
                return rows, f"naver:{nc}"
        except Exception as e:
            print(f"    · naver {nc} 실패: {e}")
    ssym = _to_stooq(tk)
    if ssym:
        try:
            rows = _fetch_stooq(ssym, days)
            if len(rows) >= 5:
                return rows, f"stooq:{ssym}"
        except Exception as e:
            print(f"    · stooq {ssym} 실패: {e}")
    ysym = _to_yahoo(tk)
    if ysym:
        try:
            return market_data._fetch_yahoo(ysym, days), f"yahoo:{ysym}"
        except Exception as e:
            print(f"    · yahoo {ysym} 실패: {e}")
    return [], ""


def backfill_history(days: int = 1825):
    """gsheet/ 티커 과거 이력 백필 — stooq(Actions에서도 됨) 우선, 실패 시 Yahoo(로컬).

    기본 5년치(=1825일). 매크로 관점의 장기 추세를 위해 넉넉히 받는다.
    브라우저에서 Actions `backfill` 모드로 돌리면 맥 없이도 stooq로 채워진다.
    기존 날짜·티커는 보존(오늘 실측 유지), 빈 곳만 채운다. 거래량도 함께.
    """
    from modes.investment import portfolio
    sections, _ = portfolio.load()
    tickers = [s.split("/", 1)[1] for _, items in sections for s, _ in items
               if s.startswith("gsheet/")]
    by_date = _read_by_date()
    # 구글 시트 이력 탭이 있으면 그게 1순위다. 구글 서버가 대신 받아오므로
    # Yahoo 429·데이터센터 IP 차단에 걸리지 않는다 — stooq/Yahoo가 못 채우던
    # 국채·원자재·환율이 이 경로로 들어온다.
    sheet_hist = fetch_sheet_history()
    if sheet_hist:
        print(f"  📗 이력 시트에서 {len(sheet_hist)}종목 확보 (1순위 소스)")
    ok = 0
    for tk in tickers:
        rows, src = (sheet_hist[tk], "시트 이력") if tk in sheet_hist \
            else _backfill_one(tk, days)
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
