"""주도주 상대강도(RS) · 수급 신호.

RS = 주도주 종가 ÷ 벤치마크(섹터/지수) 종가. 순수 가격 비율이므로
거래량 정보는 없다 → 매집/분산 비율(상승일 거래량 ÷ 하락일 거래량)을 병행.

해석:
- 주도주 이탈(RS 하락 + 분산 우위)은 지수 다이버전스보다 먼저 뜨는 천장 경보
- 조정 후 주도주가 지수보다 먼저 회복(RS 상승)하면 진성 반등의 방증

portfolio.md에서 `@벤치마크`가 붙은 종목이 대상.
"""
from modes.investment.indicators import trend_pct

TITLE = "주도주 상대강도(RS) · 수급"

WINDOW = 20          # RS 추세·수급 판정 구간 (거래일)
EXTREME_LOOKBACK = 60  # RS 신고가/신저가 판정 구간
RS_TREND_PCT = 2.0   # RS 추세 인정 임계값 (기간 전체 변화율)
ACC_STRONG = 1.2     # 매집 우위: 상승일 거래량이 하락일의 1.2배 이상
ACC_WEAK = 0.8       # 분산 우위: 0.8배 이하


def analyze(rows, bench_rows, window: int = WINDOW):
    """RS 추세 + 매집/분산 비율. 정렬은 공통 거래일 기준 (시장 휴장일 차이 흡수)."""
    bmap = {r["date"]: r["close"] for r in bench_rows if r["close"]}
    ratios = []
    for r in rows:
        b = bmap.get(r["date"])
        if b:
            ratios.append(r["close"] / b)
    if len(ratios) < window + 1:
        return {"insufficient": len(ratios)}

    rs_trend = trend_pct(ratios[-window:])
    recent = ratios[-EXTREME_LOOKBACK:]
    rs_high = ratios[-1] >= max(recent)
    rs_low = ratios[-1] <= min(recent)

    up_vol = down_vol = 0.0
    tail = [r for r in rows if r.get("volume")][-(window + 1):]
    for prev, cur in zip(tail, tail[1:]):
        if cur["close"] > prev["close"]:
            up_vol += cur["volume"]
        elif cur["close"] < prev["close"]:
            down_vol += cur["volume"]
    if down_vol:
        acc_ratio = round(up_vol / down_vol, 2)
    elif up_vol:
        acc_ratio = float("inf")  # 하락일 거래가 아예 없음 — 완전 매집
    else:
        acc_ratio = None

    if rs_trend >= RS_TREND_PCT and acc_ratio is not None and acc_ratio >= ACC_STRONG:
        verdict = "💪 주도주 건재 — RS 상승 + 매집 우위"
    elif rs_trend <= -RS_TREND_PCT and acc_ratio is not None and acc_ratio <= ACC_WEAK:
        verdict = "🚨 주도주 이탈 경고 — RS 하락 + 분산 우위 (천장 선행 신호 후보)"
    elif rs_trend <= -RS_TREND_PCT:
        verdict = "⚠️ RS 약화 — 수급은 아직 중립, 추이 확인"
    elif rs_trend >= RS_TREND_PCT:
        verdict = "🙂 RS 개선 — 거래량 확인 필요"
    else:
        verdict = "➖ 중립"

    return {
        "rs_trend_pct": round(rs_trend, 2),
        "acc_ratio": acc_ratio,
        "rs_high": rs_high,
        "rs_low": rs_low,
        "verdict": verdict,
    }


def run(ctx):
    benches = ctx.get("benchmarks", {})
    if not benches:
        return None
    lines = [f"### {TITLE} (최근 {WINDOW}거래일)"]
    found = False
    for sym, bench in benches.items():
        rows = ctx["histories"].get(sym)
        brows = ctx["histories"].get(bench)
        name = ctx["names"].get(sym, sym)
        bname = ctx["names"].get(bench, bench)
        if not rows or not brows:
            continue
        found = True
        r = analyze(rows, brows)
        if "insufficient" in r:
            lines.append(f"- {name} vs {bname}: 공통 거래일 {r['insufficient']}일 — "
                         f"데이터 축적 부족, 판정 보류 (상장 초기 종목)")
            continue
        extra = " · RS 60일 신고가" if r["rs_high"] else (" · RS 60일 신저가" if r["rs_low"] else "")
        if r["acc_ratio"] is None:
            acc = "산출 불가"
        elif r["acc_ratio"] == float("inf"):
            acc = "∞ (하락일 거래 없음)"
        else:
            acc = f"{r['acc_ratio']}배"
        lines.append(f"- {name} vs {bname}: RS 추세 {r['rs_trend_pct']:+.1f}%, "
                     f"매집/분산 {acc} → {r['verdict']}{extra}")
    if not found:
        lines.append("- (주도주/벤치마크 데이터 부족)")
    return "\n".join(lines)
