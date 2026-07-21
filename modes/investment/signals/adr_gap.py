"""SK하이닉스 본주(한국) vs 미국 ADR 괴리 — 프리미엄/디스카운트.

ADR의 원화환산가를 환율·비율로 구해 본주와 비교한다.
  ADR원화환산 = ADR($) × (원/달러) ÷ (1 ADR당 원주 수)
  괴리(프리미엄%) = ADR원화환산 / 본주 − 1
+면 ADR 고평가(해외 수요·차익 프리미엄), −면 디스카운트(국내 대비 약세).

데이터 출처:
  본주 naver/000660(KRW), ADR gsheet/NASDAQ:SKHY(USD), 환율 gsheet/CURRENCY:USDKRW.
  → 시트에 SKHY·USDKRW 줄이 있어야 하고, 이력은 백필로 채워진다.
ADR 비율은 SK하이닉스 SKHY 기준 1:1 (검색 확인). 다르면 CONFIG["ratio"] 조정.
"""
from modes.investment.charts import sparkline

TITLE = "본주 vs ADR 괴리 (SK하이닉스)"

CONFIG = {
    "main": "naver/000660",
    "adr": "gsheet/NASDAQ:SKHY",
    "fx": "gsheet/CURRENCY:USDKRW",
    "ratio": 1.0,   # 1 ADR = 원주 N주 (SKHY 1:1). 다르면 여기만 수정.
}


def _premium_series(main, adr, fx, ratio):
    """공통 거래일별 (날짜, 프리미엄%) 시계열."""
    md = {r["date"]: r["close"] for r in main}
    fd = {r["date"]: r["close"] for r in fx}
    out = []
    for r in adr:
        d, ap = r["date"], r["close"]
        m, x = md.get(d), fd.get(d)
        if m and x and ratio:
            out.append((d, (ap * x / ratio / m - 1) * 100))
    return out


def run(ctx):
    h = ctx["histories"]
    main, adr, fx = h.get(CONFIG["main"]), h.get(CONFIG["adr"]), h.get(CONFIG["fx"])
    lines = [f"### {TITLE}"]

    missing = [CONFIG[k] for k in ("main", "adr", "fx") if not h.get(CONFIG[k])]
    if missing:
        lines.append(f"- (데이터 대기: {', '.join(missing)} — 구글시트에 `NASDAQ:SKHY`·"
                     "`CURRENCY:USDKRW` 추가 후 backfill 필요)")
        return "\n".join(lines)

    ratio = CONFIG["ratio"]
    series = _premium_series(main, adr, fx, ratio)
    if not series:
        lines.append("- (본주·ADR·환율 공통 거래일이 아직 없음 — 이력 누적/백필 대기)")
        return "\n".join(lines)

    mp, ap, rate = main[-1]["close"], adr[-1]["close"], fx[-1]["close"]
    adr_krw = ap * rate / ratio
    prem = series[-1][1]

    if prem >= 3:
        verdict = "🔴 ADR 프리미엄 과열 — 해외 수요 강함 (본주 저평가 or ADR 고평가, 차익 주시)"
    elif prem >= 1:
        verdict = "🟡 ADR 소폭 프리미엄"
    elif prem > -1:
        verdict = "🟢 괴리 미미 — 본주·ADR 균형"
    elif prem > -3:
        verdict = "🟡 ADR 소폭 디스카운트"
    else:
        verdict = "🔵 ADR 디스카운트 — 해외 수요 약함 (본주 대비 저평가)"

    prems = [p for _, p in series[-60:]]
    trend = ""
    if len(prems) >= 5:
        recent = sum(prems[-5:]) / 5
        base = sum(prems[:5]) / 5
        arrow = "확대" if recent > base + 0.3 else ("축소" if recent < base - 0.3 else "횡보")
        trend = f" · 60일 추세 {sparkline(prems)} ({arrow})"

    lines.append(f"- 본주 {mp:,.0f}원 / ADR ${ap:,.2f} × {rate:,.0f} ÷ {ratio:g} = "
                 f"{adr_krw:,.0f}원 환산")
    lines.append(f"- 괴리(ADR 프리미엄): {prem:+.2f}% → {verdict}{trend}")
    return "\n".join(lines)
