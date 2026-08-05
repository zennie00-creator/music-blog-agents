"""DRAM·NAND 현물가(스팟) — DRAMeXchange 공개 표에서 수집.

thesis 기둥3의 '일일 현물가: 오르는 중이냐, 멈췄냐, 꺾였냐'를 뉴스 해석이 아니라
실제 숫자로 판정하기 위한 소스. DRAMeXchange(TrendForce) 메인 페이지는 로그인 없이
DRAM/Flash 등 품목별 Session Average와 Session Change(%)를 공개한다.

수집값은 market_history/dram_spot.jsonl에 매일 누적한다(Actions가 커밋) →
시간이 지나면 전일 대비뿐 아니라 N일 추세·방향 전환까지 판정할 수 있다.

접근이 막히면(데이터센터 IP 차단 등) 조용히 빈 값을 돌려주고, 브리핑은 기존
뉴스 기반 메모리 워치로 계속 굴러간다.
"""
import json
import os
import re
from datetime import date as _date
from html.parser import HTMLParser

import requests

from core import config

URL = "https://www.dramexchange.com/"
LOG_PATH = os.path.join(config.ROOT_DIR, "market_history", "dram_spot.jsonl")

_UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# 품목명으로 인식할 접두사 (메모리 규격) — 광고·뉴스 행을 걸러낸다.
_ITEM_RE = re.compile(r"^(DDR\d|LPDDR|GDDR|SLC|MLC|TLC|eMMC|UFS|\d+Gb|\d+GB)", re.I)

# 브리핑에서 우선 보여줄 핵심 품목 (없으면 수집된 것 중 앞쪽 사용)
KEY_ITEMS = [
    "DDR5 16Gb (2Gx8) 4800/5600",
    "DDR4 16Gb (2Gx8) 3200",
    "DDR4 8Gb (1Gx8) 3200",
]


class _TableParser(HTMLParser):
    """<table>의 행·셀 텍스트만 뽑는 최소 파서 (외부 의존성 없이)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self._rows, self._cells, self._buf = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._rows = []
        elif tag == "tr" and self._rows is not None:
            self._cells = []
        elif tag in ("td", "th") and self._cells is not None:
            self._buf = []

    def handle_data(self, data):
        if self._buf is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._buf is not None:
            self._cells.append(" ".join("".join(self._buf).split()))
            self._buf = None
        elif tag == "tr" and self._cells is not None:
            if self._cells:
                self._rows.append(self._cells)
            self._cells = None
        elif tag == "table" and self._rows is not None:
            if self._rows:
                self.tables.append(self._rows)
            self._rows = None


def _num(s):
    """'51.333' / '+0.29 %' / '-0.44%' → float. 실패 시 None."""
    if not s:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s.replace(",", ""))
    return float(m.group()) if m else None


def _col_index(header, *keywords):
    """헤더 행에서 키워드를 모두 포함하는 컬럼 인덱스 (없으면 None).
    컬럼 순서가 바뀌어도 이름으로 찾으므로 견딘다."""
    for i, cell in enumerate(header):
        low = cell.lower()
        if all(k in low for k in keywords):
            return i
    return None


def parse(html: str) -> dict:
    """페이지 HTML → {품목명: {"avg": 세션평균, "chg": 변화율%}}.

    표 구조에 의존하지 않고 헤더 이름으로 컬럼을 찾는다 — 'Session Average',
    'Session Change'(주간 표는 'Average Change')."""
    p = _TableParser()
    try:
        p.feed(html)
    except Exception:
        pass
    out = {}
    for rows in p.tables:
        header = next((r for r in rows if _col_index(r, "item") is not None
                       or _col_index(r, "session", "average") is not None), None)
        if not header:
            continue
        i_avg = _col_index(header, "session", "average")
        i_chg = (_col_index(header, "session", "change")
                 or _col_index(header, "average", "change"))
        if i_avg is None:
            continue
        for r in rows:
            if r is header or not r or not _ITEM_RE.match(r[0]):
                continue
            avg = _num(r[i_avg]) if len(r) > i_avg else None
            chg = _num(r[i_chg]) if i_chg is not None and len(r) > i_chg else None
            if avg is not None:
                out[r[0]] = {"avg": avg, "chg": chg}
    return out


def fetch(timeout: int = 20):
    """공개 표에서 스팟 가격 수집 → (items, 실패사유). 실패 시 ({}, 사유)."""
    try:
        r = requests.get(URL, headers=_UA, timeout=timeout)
        r.raise_for_status()
        items = parse(r.text)
        if not items:
            return {}, "200이지만 스팟 표를 찾지 못함 (페이지 구조 변경 가능)"
        return items, None
    except Exception as e:
        return {}, f"{type(e).__name__} {str(e)[:100]}"


# ── 이력 누적 ────────────────────────────────────────────

def _load():
    hist = {}
    if not os.path.exists(LOG_PATH):
        return hist
    with open(LOG_PATH, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if rec.get("date"):
                hist[rec["date"]] = rec.get("items", {})
    return hist


def _save(today, items):
    hist = _load()
    hist[today] = items
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        for d in sorted(hist):
            f.write(json.dumps({"date": d, "items": hist[d]}, ensure_ascii=False) + "\n")


def _trend(hist, item, today, lookback=5):
    """저장 이력에서 N거래일 전 대비 변화율(%) — 이력이 없으면 None."""
    dates = sorted(d for d in hist if d < today and item in hist[d])
    if not dates:
        return None
    old = hist[dates[max(0, len(dates) - lookback)]][item].get("avg")
    cur = hist[today][item].get("avg") if today in hist else None
    if not old or not cur:
        return None
    return (cur / old - 1) * 100


def markdown(today: str = "") -> str:
    """브리핑용 섹션. 수집 실패 시 빈 문자열(뉴스 기반 워치가 대신 커버)."""
    today = today or _date.today().isoformat()
    items, err = fetch()
    if not items:
        print(f"  🔻 DRAM 스팟 수집 실패 — {err}")
        return ""
    _save(today, items)
    hist = _load()
    print(f"  💾 DRAM 스팟 {len(items)}개 품목 수집·누적")

    keys = [k for k in KEY_ITEMS if k in items] or list(items)[:4]
    lines = ["### 반도체 현물가 (DRAMeXchange 스팟)"]
    for k in keys:
        v = items[k]
        chg = v.get("chg")
        arrow = "→" if chg in (None, 0) else ("▲" if chg > 0 else "▼")
        part = f"- {k}: {v['avg']:,.3f} {arrow}"
        if chg is not None:
            part += f" {chg:+.2f}%"
        t = _trend(hist, k, today)
        if t is not None:
            part += f" (최근 누적 {t:+.1f}%)"
        lines.append(part)
    if len(items) > len(keys):
        lines.append(f"- (그 외 {len(items) - len(keys)}개 품목 수집·누적 중)")
    return "\n".join(lines)
