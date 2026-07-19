"""반등 품질 · 패턴 신호 (재진입 판단용).

다이버전스가 '팔 때'를 본다면, 이 신호는 조정 이후 '다시 살 때'를 본다:

- 진성 반등: 반등 구간의 거래량이 하락기보다 실려 있고 RSI가 55 이상 회복
- 약한 반등: 거래량 미동반 반등 — 데드캣 바운스 / 헤드앤숄더 우측 어깨 위험.
  넥라인(직전 저점) 이탈 여부가 다음 관전 포인트
- 바닥 탐색: 아직 반등 전. 가격은 저점을 낮추는데 RSI 저점이 높아지는
  RSI 강세 다이버전스가 나오면 바닥 신호로 플래그
- 헤드앤숄더 의심: 최근 세 고점이 어깨-머리-어깨 형태면 넥라인 레벨과
  현재가 이격을 표시
"""
from modes.investment.indicators import rsi_series, local_maxima, local_minima

TITLE = "반등 품질 · 패턴 (재진입 신호, 최근 60거래일)"

WINDOW = 60            # 분석 구간 (거래일)
MIN_DRAWDOWN = 5.0     # 이만큼(%) 이상 조정이 있어야 반등 분석 대상
MIN_REBOUND = 2.0      # 저점 대비 이만큼(%) 이상 올라야 '반등 중'으로 판정
GENUINE_VOL_RATIO = 1.05   # 반등 거래량/하락기 거래량 비율이 이 이상이면 진성 쪽
WEAK_VOL_RATIO = 0.85      # 이 미만이면 거래량 미동반 반등


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def detect_head_shoulders(closes, order: int = 3, shoulder_tol: float = 0.05,
                          min_head_gap: float = 0.02):
    """최근 세 국소 고점이 어깨-머리-어깨 형태인지 검사. 아니면 None."""
    peaks = local_maxima(closes, order)
    if len(peaks) < 3:
        return None
    l, h, r = peaks[-3], peaks[-2], peaks[-1]
    left, head, right = closes[l], closes[h], closes[r]
    if head <= left * (1 + min_head_gap) or head <= right * (1 + min_head_gap):
        return None
    if abs(left - right) / head > shoulder_tol:
        return None
    neckline = (min(closes[l:h + 1]) + min(closes[h:r + 1])) / 2
    current = closes[-1]
    return {
        "neckline": neckline,
        "vs_neckline_pct": round((current - neckline) / neckline * 100, 2),
        "head": head,
        "right_shoulder": right,
    }


def analyze(rows, window: int = WINDOW):
    """조정→반등 국면 분석. 의미 있는 조정이 없으면 None."""
    usable = [r for r in rows if r.get("volume") and r["volume"] > 0]
    if len(usable) < 30:
        return None
    recent = usable[-window:]
    closes = [r["close"] for r in recent]
    vols = [r["volume"] for r in recent]
    n = len(closes)

    peak_i = max(range(n), key=lambda i: closes[i])
    if peak_i >= n - 2:
        return None  # 고점 경신 중 — 조정 국면 아님
    trough_i = min(range(peak_i, n), key=lambda i: closes[i])
    peak, trough, last = closes[peak_i], closes[trough_i], closes[-1]

    drawdown = (trough - peak) / peak * 100
    if drawdown > -MIN_DRAWDOWN:
        return None  # 의미 있는 조정 없음

    rsi = rsi_series(closes)
    rsi_now = rsi[-1]
    rebound_pct = (last - trough) / trough * 100

    result = {
        "peak": peak, "trough": trough, "last": last,
        "drawdown_pct": round(drawdown, 2),
        "rebound_pct": round(rebound_pct, 2),
        "rsi": round(rsi_now, 1) if rsi_now is not None else None,
        "hs": detect_head_shoulders(closes),
        "rsi_bullish_divergence": False,
    }

    if trough_i >= n - 1 or rebound_pct < MIN_REBOUND:
        result["phase"] = "bottoming"
        # RSI 강세 다이버전스: 가격 저점은 낮아지는데 RSI 저점은 높아짐
        minima = [i for i in local_minima(closes) if rsi[i] is not None]
        if len(minima) >= 2:
            i1, i2 = minima[-2], minima[-1]
            if closes[i2] < closes[i1] and rsi[i2] > rsi[i1]:
                result["rsi_bullish_divergence"] = True
        return result

    result["phase"] = "rebounding"
    decline_vols = vols[peak_i:trough_i + 1]
    up_day_vols = [vols[i] for i in range(trough_i + 1, n) if closes[i] > closes[i - 1]]
    vol_ratio = _mean(up_day_vols) / _mean(decline_vols) if decline_vols and up_day_vols else None
    result["vol_ratio"] = round(vol_ratio, 2) if vol_ratio else None
    result["retrace_pct"] = round((last - trough) / (peak - trough) * 100, 1)

    if vol_ratio and vol_ratio >= GENUINE_VOL_RATIO and rsi_now and rsi_now >= 55:
        result["verdict"] = "genuine"
    elif (vol_ratio and vol_ratio < WEAK_VOL_RATIO) or (rsi_now and rsi_now < 50):
        result["verdict"] = "weak"
    else:
        result["verdict"] = "mixed"
    return result


def _format(name, r):
    base = (f"- {name}: 고점 대비 {r['drawdown_pct']:+.1f}% 조정, "
            f"저점 대비 {r['rebound_pct']:+.1f}%, RSI {r['rsi']}")
    if r["phase"] == "bottoming":
        line = base + " → 🔎 바닥 탐색 중"
        if r["rsi_bullish_divergence"]:
            line += " · ✳️ RSI 강세 다이버전스 (가격 저점↓ RSI 저점↑ — 바닥 신호 후보)"
    else:
        verdict = {
            "genuine": "✅ 진성 반등 신호 (거래량 동반 + RSI 회복)",
            "weak": f"⚠️ 약한 반등 — 거래량 미동반 (데드캣/우측 어깨 위험, 넥라인 {r['trough']:,.0f})",
            "mixed": "➖ 혼조 — 거래량·RSI 확인 지속 필요",
        }[r["verdict"]]
        line = (base + f", 반등 거래량/하락기 {r['vol_ratio']}배, "
                f"되돌림 {r['retrace_pct']}% → {verdict}")
    if r["hs"]:
        hs = r["hs"]
        line += (f"\n  - 🚨 헤드앤숄더 의심 패턴: 넥라인 {hs['neckline']:,.0f} "
                 f"대비 현재 {hs['vs_neckline_pct']:+.1f}% (이탈 시 하락 전환 위험)")
    return line


def run(ctx):
    lines = [f"### {TITLE}"]
    found = False
    for sym, rows in ctx["histories"].items():
        r = analyze(rows)
        if not r:
            continue
        found = True
        lines.append(_format(ctx["names"].get(sym, sym), r))
    if not found:
        lines.append("- 의미 있는 조정(-5% 이상) 국면인 자산 없음")
    return "\n".join(lines)
