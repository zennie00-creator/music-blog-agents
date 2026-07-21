"""RSS 뉴스 수집 — 당일 헤드라인을 분석 프롬프트에 공급.

Grok 라이브 검색이 죽어도(현재 xAI 410) 당일 뉴스 차원을 잃지 않도록,
공개 RSS(블룸버그·CNBC·로이터·마켓워치 등)를 긁어 최근 헤드라인을 뽑는다.
무키·무료이고 GitHub Actions 데이터센터 IP에서도 동작한다.
피드는 sources.md의 `## RSS 피드` 섹션으로 가감 (없으면 sources.DEFAULT).
"""
import re
from xml.etree import ElementTree as ET

import requests

from modes.investment import sources

_UA = {"User-Agent": "Mozilla/5.0 (compatible; invest-bot/1.0; +rss)"}


def _text(el):
    return (el.text or "").strip() if el is not None else ""


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def parse_feed(xml_text: str, source: str = ""):
    """RSS 2.0 / Atom XML → [{title, source, published}]. 실패 시 []."""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        title, pub = "", ""
        for ch in node:
            ctag = ch.tag.split("}")[-1]
            if ctag == "title" and not title:
                title = _strip_html(_text(ch))
            elif ctag in ("pubDate", "published", "updated") and not pub:
                pub = _text(ch)
        if title:
            items.append({"title": title, "source": source, "published": pub})
    return items


def fetch_headlines(max_per_feed: int = 5, max_total: int = 24, timeout: int = 8):
    """설정된 RSS 피드에서 최근 헤드라인 수집. 피드별 성공/실패를 로그로 남김."""
    feeds = sources.rss_feeds()
    if not feeds:
        return []
    out = []
    for name, url in feeds:
        try:
            r = requests.get(url, headers=_UA, timeout=timeout)
            r.raise_for_status()
            got = parse_feed(r.text, name)[:max_per_feed]
            out.extend(got)
            print(f"  📰 {name}: {len(got)}건")
        except Exception as e:
            print(f"  ⚠️ RSS 실패 {name}: {e}")
    return out[:max_total]


def headlines_markdown(max_total: int = 24) -> str:
    """분석 프롬프트에 넣을 헤드라인 블록. 수집 0건이면 빈 문자열."""
    items = fetch_headlines(max_total=max_total)
    if not items:
        return ""
    lines = ["아래는 방금 수집한 최근 뉴스 헤드라인입니다 (RSS, 시간순 아님):", ""]
    for it in items:
        src = f"[{it['source']}] " if it["source"] else ""
        lines.append(f"- {src}{it['title']}")
    return "\n".join(lines)
