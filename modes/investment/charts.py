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


def _winsorize_volumes(recent):
    """거래량 → 0~100 상대치. 소스(시트 당일 vs 네이버 백필) 스케일 차이로
    한 점만 거대해지는 걸 막고(중앙값 3배로 winsorize), 축이 숨김이라 절대값은
    의미 없으므로 0~100으로 압축해 URL 길이도 줄인다. (0은 그대로 0)."""
    import statistics
    vols = [float(r.get("volume") or 0) for r in recent]
    nz = [v for v in vols if v > 0]
    if not nz:
        return [0] * len(vols), False
    cap = statistics.median(nz) * 3  # 중앙값의 3배로 상한 (winsorize)
    capped = [min(v, cap) for v in vols]
    hi = max(capped) or 1
    return [round(v / hi * 100) for v in capped], True  # 0~100 상대 높이


def quickchart_url(title: str, rows, days: int = 120, points: int = 28,
                   width: int = 680, height: int = 340) -> str:
    """일별 시세 rows → 종가 라인 + 거래량 바 차트 이미지 URL.

    자기완결 인라인 URL 우선(QuickChart 단축URL은 rate-limit/만료로 Notion에서
    깨질 수 있음). 한도(≤~1900자) 초과 시에만 단축URL 폴백.
    거래량은 이상치 상한 처리해 스케일 깨짐을 방지한다.
    """
    recent = rows[-days:]
    if len(recent) > points:
        step = len(recent) / points
        recent = [recent[int(i * step)] for i in range(points - 1)] + [recent[-1]]

    labels = [r["date"][5:] for r in recent]  # MM-DD
    closes = [round(r["close"], 2) for r in recent]
    volumes, has_vol = _winsorize_volumes(recent)

    datasets = [{
        "type": "line", "label": "종가", "data": closes, "yAxisID": "p",
        "borderColor": "#2563eb", "borderWidth": 2, "fill": False,
        "pointRadius": 0, "tension": 0.15,
    }]
    y_axes = [{"id": "p", "position": "left"}]
    if has_vol:
        datasets.append({
            "type": "bar", "label": "거래량", "data": volumes, "yAxisID": "v",
            "backgroundColor": "rgba(148,163,184,0.45)",
        })
        y_axes.append({"id": "v", "position": "right", "display": False,
                       "ticks": {"beginAtZero": True}})

    config = {
        "type": "bar",
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "title": {"display": True, "text": title},
            "legend": {"display": False},
            "scales": {"yAxes": y_axes, "xAxes": [{"ticks": {"maxTicksLimit": 8}}]},
        },
    }
    c = urllib.parse.quote(json.dumps(config, separators=(",", ":"), ensure_ascii=False))
    inline = f"https://quickchart.io/chart?w={width}&h={height}&bkg=white&c={c}"
    if len(inline) <= 1900:
        return inline
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
