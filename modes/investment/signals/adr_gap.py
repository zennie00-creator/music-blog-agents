"""SK하이닉스 본주(한국) vs 미국 ADR 괴리 — 프리미엄/디스카운트 (자동 보정).

핵심 관계: ADR($) × (원/달러) ÷ 본주(원) = (1 ADR당 원주 수 k) × (1 + 프리미엄).
ADR·본주는 환율을 통해 같이 움직이므로 이 값은 대체로 안정적이고, 그 중앙값이
구조적 비율 k다. 오늘 값이 그 중앙값보다 높으면 ADR 프리미엄, 낮으면 디스카운트.

이렇게 하면 공식 ADR 비율(1:1? 1/10?)을 몰라도 실데이터가 알아서 보정한다.
CONFIG["ratio"]에 숫자를 넣으면 그 값으로 고정(자동추정 대신).

데이터: 본주 naver/000660(KRW), ADR gsheet/NASDAQ:SKHY(USD), 환율 gsheet/CURRENCY:USDKRW.
"""
import statistics

from modes.investment.charts import sparkline

TITLE = "본주 vs ADR 괴리 (SK하이닉스)"

CONFIG = {
    "main": "naver/000660",
    "adr": "gsheet/NASDAQ:SKHY",
    "fx": "gsheet/CURRENCY:USDKRW",
    "ratio": None,   # None=실데이터에서 자동 추정. 숫자로 고정하려면 예: 0.125
}


def _implied_series(main, adr, fx):
    """공통 거래일별 (날짜, ADR원화환산/본주) = k×(1+프리미엄) 시계열."""
    md = {r["date"]: r["close"] for r in main}
    fd = {r["date"]: r["close"] for r in fx}
    out = []
    for r in adr:
        d, ap = r["date"], r["close"]
        m, x = md.get(d), fd.get(d)
        if m and x:
            out.append((d, ap * x / m))
    return out


def _verdict(prem):
    if prem >= 3:
        return "🔴 ADR 프리미엄 과열 — 해외 수요 강함 (본주 상대 저평가, 차익 주시)"
    if prem >= 1:
        return "🟡 ADR 소폭 프리미엄"
    if prem > -1:
        return "🟢 괴리 미미 — 본주·ADR 균형"
    if prem > -3:
        return "🟡 ADR 소폭 디스카운트"
    return "🔵 ADR 디스카운트 — 본주 대비 저평가 (해외 수요 약함)"


def run(ctx):
    h = ctx["histories"]
    main, adr, fx = h.get(CONFIG["main"]), h.get(CONFIG["adr"]), h.get(CONFIG["fx"])
    lines = [f"### {TITLE}"]

    missing = [CONFIG[k] for k in ("main", "adr", "fx") if not h.get(CONFIG[k])]
    if missing:
        lines.append(f"- (데이터 대기: {', '.join(missing)} — 시트에 `NASDAQ:SKHY`·"
                     "`CURRENCY:USDKRW` 추가 후 backfill 필요)")
        return "\n".join(lines)

    series = _implied_series(main, adr, fx)
    if not series:
        lines.append("- (본주·ADR·환율 공통 거래일 없음 — 이력 누적/백필 대기)")
        return "\n".join(lines)

    vals = [v for _, v in series]
    k = CONFIG["ratio"] or statistics.median(vals)  # 구조적 비율 (고정 or 자동)
    if not k:
        lines.append("- (비율 추정 불가)")
        return "\n".join(lines)

    prem_series = [(d, (v / k - 1) * 100) for d, v in series]
    prem = prem_series[-1][1]
    mp, ap, rate = main[-1]["close"], adr[-1]["close"], fx[-1]["close"]

    src = "고정" if CONFIG["ratio"] else f"실데이터 {len(vals)}일 자동추정"
    lines.append(f"- 구조적 비율: **1 ADR ≈ {k:.3f}주** (본주 1주 ≈ {1/k:.1f} ADR) · {src}")
    lines.append(f"- 오늘: 본주 {mp:,.0f}원 / ADR ${ap:,.2f} × {rate:,.0f} = {ap*rate:,.0f}원 환산")
    trend = ""
    prems = [p for _, p in prem_series[-60:]]
    if len(prems) >= 5:
        arrow = ("확대" if sum(prems[-5:]) / 5 > sum(prems[:5]) / 5 + 0.3
                 else "축소" if sum(prems[-5:]) / 5 < sum(prems[:5]) / 5 - 0.3 else "횡보")
        trend = f" · 60일 {sparkline(prems)} ({arrow})"
    lines.append(f"- 괴리(ADR 프리미엄): {prem:+.2f}% → {_verdict(prem)}{trend}")
    return "\n".join(lines)
