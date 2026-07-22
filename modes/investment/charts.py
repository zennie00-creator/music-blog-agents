"""시각화 — 유니코드 스파크라인 + QuickChart 차트 이미지 URL.

- sparkline: 대시보드 표 안에서 60일 추세를 8단계 블록 문자로 표시.
  (LLM 프롬프트에 들어가도 토큰 부담이 거의 없음)
- quickchart_url: chart.js 설정을 URL에 담아 quickchart.io 이미지로 렌더.
  API 키·로컬 의존성 불필요. Notion 이미지 블록(external)으로 바로 임베드.
  차트는 일지 '생성 후' 붙이므로 LLM 토큰을 소모하지 않는다.
"""
import json
import urllib.parse

import requests

_BLOCKS = "▁▂▃▄▅▆▇█"


def sparkline(values, width: int = 20) -> str:
    """숫자 리스트를 폭 width의 유니코드 스파크라인으로."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return ""
    if len(vals) > width:
        step = len(vals) / width
        vals = [vals[int(i * step)] for i in range(width - 1)] + [vals[-1]]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return _BLOCKS[3] * len(vals)
    return "".join(_BLOCKS[int((v - lo) / (hi - lo) * (len(_BLOCKS) - 1))] for v in vals)


def quickchart_url(title: str, rows, days: int = 120, points: int = 40,
                   width: int = 680, height: int = 340) -> str:
    """일별 시세 rows → 종가 라인 + 거래량 바 차트 이미지 URL.

    가능한 한 '자기완결(self-contained) 인라인 URL'을 쓴다 — QuickChart 단축URL은
    무료 생성 API의 rate-limit·만료로 Notion에서 이미지가 깨질 수 있어서다.
    인라인이 Notion 한도(≤~1900자)를 넘을 때만 단축URL로 폴백한다.
    """
    recent = rows[-days:]
    if len(recent) > points:
        step = len(recent) / points
        recent = [recent[int(i * step)] for i in range(points - 1)] + [recent[-1]]

    labels = [r["date"][5:] for r in recent]  # MM-DD
    closes = [round(r["close"], 2) for r in recent]

    # 종가 추세선만 그린다. 거래량 막대는 소스(네이버 백필 vs 시트 당일)마다
    # 스케일이 달라 한 막대만 거대해져 깨지므로 제외 — 거래량은 대시보드에 있다.
    config = {
        "type": "line",
        "data": {"labels": labels, "datasets": [{
            "label": "종가", "data": closes,
            "borderColor": "#2563eb", "borderWidth": 2, "fill": False,
            "pointRadius": 0, "tension": 0.15,
        }]},
        "options": {
            "title": {"display": True, "text": title},
            "legend": {"display": False},
            "scales": {"xAxes": [{"ticks": {"maxTicksLimit": 8}}]},
        },
    }
    c = urllib.parse.quote(json.dumps(config, separators=(",", ":"), ensure_ascii=False))
    inline = f"https://quickchart.io/chart?w={width}&h={height}&bkg=white&c={c}"
    if len(inline) <= 1900:
        return inline  # 안정적인 자기완결 URL
    return _short_chart_url(config, width, height) or inline


def _short_chart_url(config, width, height):
    """QuickChart create API로 짧은 이미지 URL 발급 (실패 시 None)."""
    try:
        r = requests.post(
            "https://quickchart.io/chart/create",
            json={"chart": config, "width": width, "height": height,
                  "backgroundColor": "white"},
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("url") or None
    except Exception as e:
        print(f"  ⚠️ 차트 단축 URL 실패 (인라인 폴백): {e}")
        return None


CHART_SECTION_KEYWORDS = ("지수", "섹터", "주도주")
MAX_CHARTS = 6
MIN_CHART_HISTORY = 20  # 이력이 짧으면(신규상장·백필 전) 차트 생략 — 2점짜리 방지


def charts_markdown(ctx, keywords=CHART_SECTION_KEYWORDS, limit: int = MAX_CHARTS) -> str:
    """지수·섹터·주도주 중 이력이 충분한 자산만 차트로. (Notion 렌더 안정 위해 소수만)"""
    lines = []
    for title, syms in ctx.get("sections", []):
        if not any(k in title for k in keywords):
            continue
        for sym in syms:
            if len(lines) >= limit:
                break
            rows = ctx["histories"][sym]
            if len(rows) < MIN_CHART_HISTORY:
                continue  # 짧은 이력은 추세가 안 보여 스킵
            name = ctx["names"].get(sym, sym)
            lines.append(f"![{name}]({quickchart_url(name, rows)})")
    return "\n".join(lines)
