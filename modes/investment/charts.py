"""시각화 — 유니코드 스파크라인 + QuickChart 차트 이미지 URL.

- sparkline: 대시보드 표 안에서 60일 추세를 8단계 블록 문자로 표시.
  (LLM 프롬프트에 들어가도 토큰 부담이 거의 없음)
- quickchart_url: chart.js 설정을 URL에 담아 quickchart.io 이미지로 렌더.
  API 키·로컬 의존성 불필요. Notion 이미지 블록(external)으로 바로 임베드.
  차트는 일지 '생성 후' 붙이므로 LLM 토큰을 소모하지 않는다.
"""
import json
import urllib.parse

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


def quickchart_url(title: str, rows, days: int = 60, points: int = 40,
                   width: int = 700, height: int = 360) -> str:
    """일별 시세 rows → 종가 라인 + 거래량 바 차트 이미지 URL."""
    recent = rows[-days:]
    if len(recent) > points:
        step = len(recent) / points
        recent = [recent[int(i * step)] for i in range(points - 1)] + [recent[-1]]

    labels = [r["date"][5:] for r in recent]  # MM-DD
    closes = [round(r["close"], 2) for r in recent]
    volumes = [round(r.get("volume") or 0) for r in recent]
    has_vol = any(volumes)

    datasets = [{
        "type": "line", "label": "종가", "data": closes, "yAxisID": "p",
        "borderColor": "#2563eb", "borderWidth": 2, "fill": False, "pointRadius": 0,
    }]
    y_axes = [{"id": "p", "position": "left"}]
    if has_vol:
        datasets.append({
            "type": "bar", "label": "거래량", "data": volumes, "yAxisID": "v",
            "backgroundColor": "rgba(148,163,184,0.45)",
        })
        y_axes.append({"id": "v", "position": "right",
                       "gridLines": {"display": False}, "ticks": {"beginAtZero": True}})

    config = {
        "type": "bar",
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "title": {"display": True, "text": title},
            "legend": {"display": has_vol},
            "scales": {"yAxes": y_axes,
                       "xAxes": [{"ticks": {"maxTicksLimit": 10}}]},
        },
    }
    c = urllib.parse.quote(json.dumps(config, separators=(",", ":"), ensure_ascii=False))
    return f"https://quickchart.io/chart?w={width}&h={height}&c={c}"


CHART_SECTION_KEYWORDS = ("지수", "섹터", "주도주")
MAX_CHARTS = 8


def charts_markdown(ctx, keywords=CHART_SECTION_KEYWORDS, limit: int = MAX_CHARTS) -> str:
    """지수·섹터·주도주 자산의 차트 이미지 마크다운(`![...](url)`) 생성."""
    lines = []
    for title, syms in ctx.get("sections", []):
        if not any(k in title for k in keywords):
            continue
        for sym in syms:
            if len(lines) >= limit:
                break
            name = ctx["names"].get(sym, sym)
            url = quickchart_url(name, ctx["histories"][sym])
            lines.append(f"![{name}]({url})")
    return "\n".join(lines)
