"""실적(어닝) 뉴스 수집 — 워치리스트 종목의 실적·가이던스·어닝콜 헤드라인.

실적 시즌에 브리핑이 개별 종목 실적을 빠뜨리지 않도록, 포트폴리오/워치리스트
종목별로 'earnings' 관련 최근 헤드라인을 Google News RSS로 긁어 분석 프롬프트에
공급한다. 실제 보도된 제목을 근거로 넣으므로 모델이 실적 결과·가이던스를
'지어내지 않고' 요약할 수 있다. Google News RSS는 무키·무료이고 GitHub Actions
데이터센터 IP에서도 동작한다 (Yahoo 429 문제 없음).

실적 보도가 없는 종목·오프시즌에는 빈 문자열을 돌려주므로 프롬프트가 붓지 않는다.
"""
from urllib.parse import quote

import requests

from modes.investment import news, portfolio

# 바 티커 → 영문 검색어 (영어 금융 매체가 실적·가이던스 보도가 풍부하다).
# 여기 없는 심볼(지수·금리·환율·ETF 등)은 실적 대상이 아니므로 자동 제외된다.
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

_MAX_COMPANIES = 12
_MAX_PER_COMPANY = 4


def _bare_ticker(symbol: str) -> str:
    """'gsheet/NASDAQ:GOOGL' → 'GOOGL', 'naver/000660' → '000660'."""
    return symbol.split("/")[-1].split(":")[-1].strip()


def watchlist_companies():
    """워치리스트에서 실적 대상 종목만 추출 → [(표시이름, 영문검색어)].

    NAME_MAP에 있는 종목만 포함(지수·금리·환율·ETF 자동 제외).
    같은 회사(예: SK하이닉스 ADR/본주)는 영문명 기준 1회만."""
    sections, _ = portfolio.load()
    out, seen = [], set()
    for _name, items in sections:
        for sym, disp in items:
            eng = NAME_MAP.get(_bare_ticker(sym))
            if not eng or eng in seen:
                continue
            seen.add(eng)
            out.append((disp, eng))
    return out[:_MAX_COMPANIES]


def _search_rss(query: str, when: str = "3d", timeout: int = 6):
    """Google News RSS 검색 → news.parse_feed 형식 아이템. 실패 시 []."""
    q = quote(f'"{query}" earnings when:{when}')
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        r = requests.get(url, headers=news._UA, timeout=timeout)
        r.raise_for_status()
        return news.parse_feed(r.text, source="")
    except Exception as e:
        print(f"  ⚠️ 실적 뉴스 실패 {query}: {e}")
        return []


def earnings_markdown() -> str:
    """분석 프롬프트에 넣을 종목별 실적 헤드라인 블록. 보도 0건이면 빈 문자열."""
    companies = watchlist_companies()
    if not companies:
        return ""
    groups = []
    for disp, eng in companies:
        items = _search_rss(eng)[:_MAX_PER_COMPANY]
        if not items:
            continue
        label = f"{disp} ({eng})" if disp and disp != eng else eng
        lines = [f"**{label}**"]
        lines += [f"- {it['title']}" for it in items]
        groups.append("\n".join(lines))
        print(f"  📑 실적 뉴스 {eng}: {len(items)}건")
    if not groups:
        return ""
    header = ("아래는 워치리스트 종목의 최근 실적(어닝) 관련 헤드라인입니다"
              " (Google News, 최근 3일):")
    return header + "\n\n" + "\n\n".join(groups)
