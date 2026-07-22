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
    """일별 시세 rows → 종가 추세선 차트 이미지 URL.

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


def _align_volumes_real(recent):
    """거래량을 '실제 크기 그대로' 정렬 — 소스 단위 불일치만 보정, 봉우리 보존.

    _align_volumes(라인/URL용)와 달리 0~100 압축을 하지 않는다(PNG는 축이 자동
    맞춤이라 절대값 그대로 그리면 됨). 히스토리(네이버=千 단위)와 오늘치(시트=raw)가
    ~1000배 어긋나는 지점만 1000의 거듭제곱으로 되돌린다. 거래량 0(오늘 미마감 등)은
    막대를 그리지 않도록 None. 유효 거래량이 하나도 없으면 (None들, False)."""
    raw = [float(r.get("volume") or 0) for r in recent]
    nz = sorted(v for v in raw if v > 0)
    if not nz:
        return [None] * len(raw), False
    med = nz[len(nz) // 2]
    out = []
    for v in raw:
        if v <= 0:
            out.append(None)
            continue
        while v / med >= 100:
            v /= 1000
        while v / med <= 0.01:
            v *= 1000
        out.append(v)
    return out, True


def render_chart_png(rows, days: int = 120, width_px: int = 760,
                     height_px: int = 420, dpi: int = 100) -> bytes:
    """일별 시세 rows → 종가 추세선(위) + 거래량 막대(아래) PNG 바이트.

    QuickChart(외부 URL을 Notion이 가져가는 방식)를 쓰지 않고 서버에서 직접 렌더해
    Notion에 '파일'로 올린다 → 외부 fetch 실패가 원천 차단된다. 한글은 폰트 문제를
    피하려 이미지에 넣지 않고(날짜·숫자만) 종목명은 Notion 캡션으로 붙인다.
    거래량은 소스 단위만 정렬하고 봉우리는 그대로 둔다(위 안 자름)."""
    import matplotlib
    matplotlib.use("Agg")  # 디스플레이 없는 러너용
    import matplotlib.pyplot as plt

    recent = rows[-days:]
    x = list(range(len(recent)))
    closes = [r["close"] for r in recent]
    volumes, has_vol = _align_volumes_real(recent)

    if has_vol:
        fig, (ax_p, ax_v) = plt.subplots(
            2, 1, sharex=True, gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08},
            figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    else:
        fig, ax_p = plt.subplots(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
        ax_v = None

    ax_p.plot(x, closes, color="#2563eb", linewidth=2)
    ax_p.grid(True, axis="y", alpha=0.18)
    ax_p.margins(x=0.01)
    for s in ("top", "right"):
        ax_p.spines[s].set_visible(False)
    ax_p.tick_params(labelsize=8)

    if ax_v is not None:
        bars_x = [i for i, v in zip(x, volumes) if v is not None]
        bars_h = [v for v in volumes if v is not None]
        ax_v.bar(bars_x, bars_h, color="#94a3b8", width=0.8)
        ax_v.grid(True, axis="y", alpha=0.15)
        ax_v.margins(x=0.01)
        ax_v.set_yticks([])  # 거래량 절대값은 의미 약함 → 눈금 생략, 상대 높이만
        for s in ("top", "right", "left"):
            ax_v.spines[s].set_visible(False)
        axis_for_x = ax_v
    else:
        axis_for_x = ax_p

    # x축 날짜 라벨 ~8개만 (MM-DD, ASCII라 폰트 문제 없음)
    labels = [r["date"][5:] for r in recent]
    n = len(labels)
    step = max(1, n // 8)
    ticks = list(range(0, n, step))
    axis_for_x.set_xticks(ticks)
    axis_for_x.set_xticklabels([labels[i] for i in ticks], fontsize=8, rotation=0)

    import io
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white", bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return buf.getvalue()


def chart_specs(ctx, keywords=CHART_SECTION_KEYWORDS, limit: int = MAX_CHARTS):
    """지수·섹터·주도주 중 이력이 충분한 자산 → [(종목명, PNG바이트)].

    렌더 실패는 조용히 건너뛴다(브리프 본류를 막지 않음). Notion엔 파일로 업로드된다."""
    specs = []
    for title, syms in ctx.get("sections", []):
        if not any(k in title for k in keywords):
            continue
        for sym in syms:
            if len(specs) >= limit:
                break
            rows = ctx["histories"][sym]
            if len(rows) < MIN_CHART_HISTORY:
                continue  # 짧은 이력은 추세가 안 보여 스킵
            name = ctx["names"].get(sym, sym)
            try:
                specs.append((name, render_chart_png(rows)))
            except Exception as e:
                print(f"  ⚠️ 차트 렌더 실패({name}): {e}")
    return specs


def charts_markdown(ctx, keywords=CHART_SECTION_KEYWORDS, limit: int = MAX_CHARTS) -> str:
    """(구) QuickChart 인라인 URL 방식 — PNG 업로드로 대체됨. 하위호환용 유지."""
    lines = []
    for title, syms in ctx.get("sections", []):
        if not any(k in title for k in keywords):
            continue
        for sym in syms:
            if len(lines) >= limit:
                break
            rows = ctx["histories"][sym]
            if len(rows) < MIN_CHART_HISTORY:
                continue
            name = ctx["names"].get(sym, sym)
            lines.append(f"![{name}]({quickchart_url(name, rows)})")
    return "\n".join(lines)
