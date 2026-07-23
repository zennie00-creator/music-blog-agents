"""보조 뉴스 수집 — 실적(어닝)과 신용·유동성 워치.

브리핑이 개별 종목 실적을 빠뜨리지 않도록, 워치리스트 종목별로 'earnings' 관련
최근 헤드라인을 Google News RSS로 긁어 분석 프롬프트에 종목별로 공급한다.
또한 오라클 CDS·신용 스프레드처럼 '지표'로 보고 싶은 크레딧 이슈를 뉴스 기반으로
따로 워치한다 (실적과 별개 섹션). 실제 보도된 제목을 근거로 넣으므로 모델이
결과·가이던스를 '지어내지 않고' 요약할 수 있다.

Google News RSS는 무키·무료이고 GitHub Actions 데이터센터 IP에서도 동작한다.
보도가 없는 종목·오프시즌엔 빈 문자열을 돌려주므로 프롬프트가 붓지 않는다.
"""
from urllib.parse import quote

import requests

from modes.investment import news, portfolio

# 바 티커 → 영문 검색어 (영어 금융 매체가 실적·가이던스 보도가 풍부하다).
# 워치리스트에 없는 종목도 티커로 자동 검색되므로, 여기엔 '이름이 티커와 다르거나
# 영문명이 더 잘 잡히는' 종목만 둔다. 나머지는 티커를 그대로 검색어로 쓴다.
NAME_MAP = {
    "NVDA": "Nvidia",
    "MU": "Micron",
    "SKHY": "SK Hynix",
    "000660": "SK Hynix",
    "COHR": "Coherent",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "TSLA": "Tesla",
    "PLTR": "Palantir",
    "JOBY": "Joby Aviation",
    "MSTR": "MicroStrategy",
    "COIN": "Coinbase",
}

# 실적이 없는 상품(ETF·SPAC 등) — 워치리스트에 있어도 '어닝' 대상에선 제외.
NO_EARNINGS = {"IBIT", "SPCX"}

# 지수·금리·환율 심볼에 공통으로 들어가는 토큰 — 개별 종목이 아니므로 제외.
_NON_EQUITY_TOKENS = ("INDEX", "CURRENCY", "KOSPI", "KRW")

# 신용·유동성 워치 — (표시 라벨, Google News 검색어). 실적과 별개로 추적.
CREDIT_WATCH = [
    ("오라클(Oracle) 신용·CDS",
     'Oracle ("credit default swap" OR CDS OR "credit spread" OR bond OR debt OR capex)'),
]

_MAX_COMPANIES = 20
_MAX_PER_COMPANY = 4
_MAX_PER_WATCH = 4


def _bare_ticker(symbol: str) -> str:
    """'gsheet/NASDAQ:GOOGL' → 'GOOGL', 'naver/000660' → '000660'."""
    return symbol.split("/")[-1].split(":")[-1].strip()


def _is_equity(symbol: str) -> bool:
    up = symbol.upper()
    return not any(tok in up for tok in _NON_EQUITY_TOKENS)


def _search_term(ticker: str, disp: str) -> str:
    """종목별 Google News 검색어. 영문명 매핑 우선 → 미국 티커 → (한국코드 등) 표시이름."""
    if ticker in NAME_MAP:
        return NAME_MAP[ticker]
    if ticker.isalpha():          # 미국 티커(NVDA·PLTR 등)는 그대로 잘 잡힌다
        return ticker
    return disp                   # 한국 종목코드 등 숫자 티커는 표시 이름으로


def watchlist_companies():
    """워치리스트의 개별 종목 전체 → [(표시이름, 검색어)].

    지수·금리·환율(비종목)과 실적 없는 ETF는 제외. 같은 회사(예: SK하이닉스
    ADR/본주)는 검색어 기준 1회만. 워치리스트에 종목을 추가하면 자동 반영된다."""
    sections, _ = portfolio.load()
    out, seen = [], set()
    for _name, items in sections:
        for sym, disp in items:
            ticker = _bare_ticker(sym)
            if not _is_equity(sym) or ticker in NO_EARNINGS:
                continue
            term = _search_term(ticker, disp)
            if not term or term in seen:
                continue
            seen.add(term)
            out.append((disp, term))
    return out[:_MAX_COMPANIES]


def _news_rss(query: str, when: str = "3d", timeout: int = 6):
    """Google News RSS 검색 → news.parse_feed 형식 아이템. 실패 시 []."""
    q = quote(f"{query} when:{when}")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        r = requests.get(url, headers=news._UA, timeout=timeout)
        r.raise_for_status()
        return news.parse_feed(r.text, source="")
    except Exception as e:
        print(f"  ⚠️ 뉴스 검색 실패 ({query[:40]}): {e}")
        return []


def _render_group(label: str, items) -> str:
    lines = [f"**{label}**"] + [f"- {it['title']}" for it in items]
    return "\n".join(lines)


def earnings_markdown() -> str:
    """분석 프롬프트에 넣을 종목별 실적 헤드라인 블록. 보도 0건이면 빈 문자열."""
    companies = watchlist_companies()
    if not companies:
        return ""
    groups = []
    for disp, term in companies:
        items = _news_rss(f'"{term}" earnings')[:_MAX_PER_COMPANY]
        if not items:
            continue
        label = f"{disp} ({term})" if disp and disp != term else term
        groups.append(_render_group(label, items))
        print(f"  📑 실적 뉴스 {term}: {len(items)}건")
    if not groups:
        return ""
    header = ("아래는 워치리스트 종목의 최근 실적(어닝) 관련 헤드라인입니다"
              " (Google News, 최근 3일):")
    return header + "\n\n" + "\n\n".join(groups)


def credit_watch_markdown() -> str:
    """신용·유동성 워치(오라클 CDS 등) 헤드라인 블록. 보도 0건이면 빈 문자열."""
    groups = []
    for label, query in CREDIT_WATCH:
        items = _news_rss(query, when="7d")[:_MAX_PER_WATCH]
        if not items:
            continue
        groups.append(_render_group(label, items))
        print(f"  🏦 신용 워치 {label}: {len(items)}건")
    if not groups:
        return ""
    header = ("아래는 신용·유동성 워치 항목의 최근 헤드라인입니다"
              " (Google News, 최근 7일):")
    return header + "\n\n" + "\n\n".join(groups)
