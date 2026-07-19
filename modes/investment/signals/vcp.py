"""VCP 수축 감지 — Minervini의 Volatility Contraction Pattern (관찰 신호).

핵심 아이디어: 건전한 베이스에서 변동성이 점점 수축하고 거래량이 마르면
(dry-up), 매물이 소화됐다는 뜻 — 이후 거래량이 실린 돌파가 나오면 진입 후보.
반등 품질 신호가 '조정 후 반등'을 본다면, VCP는 '조정 없이 다지는 구간'을 본다.

판정 (전부 충족 시 플래그):
1. 베이스 유지: 현재가가 60일 고점 대비 -15% 이내 (깊은 조정이 아님)
2. 변동성 수축: 최근 10일 일수익률 표준편차 < 직전 20일의 65%
3. 거래량 드라이업: 최근 10일 평균 거래량 < 60일 평균의 70%
4. 피벗 근접도: 30일 고점 대비 -5% 이내면 '돌파 관찰', 그 밖이면 '수축 진행'

주의: 어디까지나 관찰 신호. 돌파 여부와 돌파일 거래량 확인은 사람이 한다.
"""
import statistics

TITLE = "VCP 수축 감지 (Minervini — 돌파 관찰 신호)"

BASE_MAX_OFF_HIGH = 0.15   # 60일 고점 대비 최대 하락폭
CONTRACTION_RATIO = 0.65   # 최근 10일 변동성 / 직전 20일 변동성 임계
DRYUP_RATIO = 0.70         # 최근 10일 거래량 / 60일 평균 임계
PIVOT_NEAR = 0.05          # 30일 고점 대비 이내면 '돌파 관찰'


def _stdev_returns(closes):
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]
    return statistics.pstdev(rets) if len(rets) >= 2 else None


def detect(rows):
    """VCP 수축 여부 판정. 조건 미달이면 None."""
    usable = [r for r in rows if r.get("volume") and r["volume"] > 0]
    if len(usable) < 60:
        return None
    recent = usable[-60:]
    closes = [r["close"] for r in recent]
    vols = [r["volume"] for r in recent]
    last = closes[-1]

    high60 = max(closes)
    if last < high60 * (1 - BASE_MAX_OFF_HIGH):
        return None  # 깊은 조정 — VCP 베이스가 아니라 반등품질 신호의 영역

    vol_recent = _stdev_returns(closes[-10:])
    vol_prior = _stdev_returns(closes[-30:-10])
    if not vol_recent or not vol_prior or vol_prior == 0:
        return None
    contraction = vol_recent / vol_prior
    if contraction > CONTRACTION_RATIO:
        return None

    avg10 = sum(vols[-10:]) / 10
    avg60 = sum(vols) / len(vols)
    dryup = avg10 / avg60 if avg60 else 1.0
    if dryup > DRYUP_RATIO:
        return None

    high30 = max(closes[-30:])
    off_pivot = (last - high30) / high30
    near_pivot = off_pivot >= -PIVOT_NEAR

    return {
        "contraction": round(contraction, 2),
        "dryup": round(dryup, 2),
        "pivot": high30,
        "off_pivot_pct": round(off_pivot * 100, 1),
        "near_pivot": near_pivot,
    }


def run(ctx):
    lines = [f"### {TITLE}"]
    found = False
    for sym, rows in ctx["histories"].items():
        v = detect(rows)
        if not v:
            continue
        found = True
        name = ctx["names"].get(sym, sym)
        stage = ("🎯 돌파 관찰 — 피벗 돌파 시 거래량 확인" if v["near_pivot"]
                 else "⏳ 수축 진행 중")
        lines.append(
            f"- {name}: 변동성 수축 {v['contraction']}배, 거래량 드라이업 {v['dryup']}배, "
            f"피벗 {v['pivot']:,.0f} 대비 {v['off_pivot_pct']:+.1f}% → {stage}"
        )
    if not found:
        return None  # 해당 없으면 섹션 자체를 생략 (노이즈 감소)
    return "\n".join(lines)
