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
    "ratio": 0.1,    # 공식 비율: 1 ADR = 0.1 원주 (10 ADR = 본주 1주).
                     # 이 원칙 대비 실제 괴리(프리미엄)를 있는 그대로 보여준다.
                     # (None으로 두면 실데이터 median으로 자동추정 — 구조적 프리미엄을 흡수함)
}


def _implied_series(main, adr, fx):
    """공통 거래일별 (날짜, ADR원화환산/본주, 본주, ADR, 환율) 시계열.
    첫 값 = k×(1+프리미엄). 본주·ADR·환율을 같은 날짜로 묶어 반환한다
    (본주·ADR 기준일이 어긋나도 항상 '같은 날' 괴리를 비교하도록)."""
    md = {r["date"]: r["close"] for r in main}
    fd = {r["date"]: r["close"] for r in fx}
    out = []
    for r in adr:
        d, ap = r["date"], r["close"]
        m, x = md.get(d), fd.get(d)
        if m and x:
            out.append((d, ap * x / m, m, ap, x))
    return out


def _verdict(dev):
    """오늘 프리미엄이 자기 평소(60일 평균) 대비 얼마나 벌어졌나(%p)로 판정."""
    if dev >= 2:
        return "🔴 프리미엄 확대 — 평소보다 과열 (해외 수요↑·본주 상대 저평가 심화)"
    if dev >= 0.7:
        return "🟡 프리미엄 소폭 확대"
    if dev > -0.7:
        return "🟢 평소 수준 유지"
    if dev > -2:
        return "🟡 프리미엄 소폭 축소"
    return "🔵 프리미엄 축소 — 해외 수요 둔화 or 본주 강세 (괴리 수렴)"


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

    vals = [t[1] for t in series]
    k = CONFIG["ratio"] or statistics.median(vals)  # 구조적 비율 (고정 or 자동)
    if not k:
        lines.append("- (비율 추정 불가)")
        return "\n".join(lines)

    prem_series = [(t[0], (t[1] / k - 1) * 100) for t in series]  # 공식 비율 대비 프리미엄%
    prem = prem_series[-1][1]
    # 표시는 '같은 공통 기준일' 값으로 통일 — 본주/ADR 기준일이 어긋나 숫자가
    # 안 맞아 보이는 문제를 막는다 (프리미엄도 이 날짜 기준으로 검산됨).
    d_common, _, mp, ap, rate = series[-1]
    adr_krw = ap * rate
    parity = mp * k  # ADR 1주의 본주 패리티(원). ADR 원화환산이 이보다 높으면 프리미엄.

    ratio_txt = "공식 1:10" if CONFIG["ratio"] == 0.1 else f"{k:.3f}주/ADR"
    lines.append(f"- 공통 기준일 {d_common}: 본주 {mp:,.0f}원 · ADR ${ap:,.2f} × {rate:,.0f} "
                 f"= {adr_krw:,.0f}원")
    lines.append(f"- {ratio_txt} 패리티(ADR 1주=본주×{k}) {parity:,.0f}원 대비 → "
                 f"ADR **{prem:+.1f}%** 프리미엄")

    # 본주에 공통일보다 최신 데이터가 있으면 (ADR 미갱신) '지금 기준'과의 시차를 알린다.
    if main[-1]["date"] > d_common:
        m_last = main[-1]
        chg = (m_last["close"] / mp - 1) * 100 if mp else 0.0
        lines.append(f"  ℹ️ 본주 최신 {m_last['date']} {m_last['close']:,.0f}원({chg:+.1f}%)은 "
                     f"ADR({d_common}) 미반영 — 다음 ADR 갱신 때 괴리 재조정 예상")

    prems = [p for _, p in prem_series[-60:]]
    n = len(prems)
    if n >= 3:
        avg = sum(prems) / n
        dev = prem - avg
        arrow = "확대" if dev > 0.3 else ("축소" if dev < -0.3 else "횡보")
        note = " ⚠️신규상장 초기" if n < 15 else ""  # SKHY는 상장 2주차 → 표본 적음
        lines.append(f"- ADR 프리미엄: **{prem:+.1f}%** (최근 {n}일 평균 {avg:+.1f}%, "
                     f"{dev:+.1f}%p {arrow}){note} {sparkline(prems)}")
        lines.append(f"  → {_verdict(dev)}")
    else:
        lines.append(f"- ADR 프리미엄: **{prem:+.1f}%** (평균 비교는 며칠 더 쌓이면 · 상장 초기)")
    return "\n".join(lines)
