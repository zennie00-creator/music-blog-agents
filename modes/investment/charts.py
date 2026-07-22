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


def _align_volumes(recent):
    """거래량 스케일 정렬 — '위를 자르지 않는다'(winsorize 아님).

    히스토리(네이버 백필: 지수는 千 단위)와 오늘치(구글시트: 지수는 raw)가 섞여
    한 점만 ~1000배로 튀는 게 문제였다. 중앙값과 100배 이상 벌어진 점만 1000의
    거듭제곱으로 되돌려 같은 단위로 맞춘다 — 진짜 급등(2~10배)은 손대지 않는다.
    거래량 0(오늘치 미제공 등)은 막대를 그리지 않고 갭(None)으로 둔다.
    표시축이 숨김이라 절대값은 무의미 → 마지막에 0~100 비율로 압축(URL 단축,
    비율 보존이라 봉우리를 안 자름)."""
    raw = [float(r.get("volume") or 0) for r in recent]
    nz = sorted(v for v in raw if v > 0)
    if not nz:
        return [None] * len(raw), False
    med = nz[len(nz) // 2]
    aligned = []
    for v in raw:
        if v <= 0:
            aligned.append(None)             # 결측 → 갭 (0 막대로 안 깨지게)
            continue
        while v / med >= 100:   # 소스 단위 불일치(지수 raw vs 千) → ÷1000
            v /= 1000
        while v / med <= 0.01:  # 반대 방향 불일치 → ×1000
            v *= 1000
        aligned.append(v)
    hi = max(v for v in aligned if v) or 1
    return [None if v is None else round(v / hi * 100) for v in aligned], True


def quickchart_url(title: str, rows, days: int = 120, points: int = 28,
                   width: int = 680, height: int = 340) -> str:
    """일별 시세 rows → 종가 라인 + 거래량 바 차트 이미지 URL.

    자기완결 인라인 URL 우선(QuickChart 단축URL은 rate-limit/만료로 Notion에서
    깨질 수 있음). 한도(≤~1900자) 초과 시에만 단축URL 폴백.
    거래량은 소스 단위 차이를 정렬(align)해 스케일 깨짐을 막되 봉우리는 보존한다.
    """
    recent = rows[-days:]
    if len(recent) > points:
        step = len(recent) / points
        recent = [recent[int(i * step)] for i in range(points - 1)] + [recent[-1]]

    labels = [r["date"][5:] for r in recent]  # MM-DD
    closes = [round(r["close"], 2) for r in recent]
    volumes, has_vol = _align_volumes(recent)

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
