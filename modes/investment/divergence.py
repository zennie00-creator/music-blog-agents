"""가격-거래량 다이버전스 감지.

다이버전스 = 주가의 방향(추세)과 거래량 추세가 반대로 움직이는 것.
특히 '가격은 오르는데 거래량이 줄어드는' 약세 다이버전스는
상승 동력 약화 신호로, 비중 축소·현금화 검토의 트리거가 된다.

계산: 최근 N거래일(기본 15일)의 종가·거래량 각각에 최소자승 추세선을 긋고,
기울기를 '기간 전체 변화율(%)'로 정규화해 비교한다.
"""

# 추세 판정 임계값 (기간 전체 변화율 기준)
PRICE_TREND_PCT = 2.0    # 가격: ±2% 이상이면 추세로 인정
VOLUME_TREND_PCT = 10.0  # 거래량: ±10% 이상이면 추세로 인정 (노이즈가 커서 넉넉하게)

SIGNALS = {
    "bearish_divergence": "🚨 약세 다이버전스 — 가격 상승 + 거래량 감소. 상승 동력 약화, 비중 조절 검토 구간",
    "seller_exhaustion": "👀 매도세 둔화 — 가격 하락 + 거래량 감소. 반등 가능성 주시",
    "distribution": "⚠️ 하락 가속 — 가격 하락 + 거래량 증가. 투매/기관 물량 소화 국면",
    "healthy_uptrend": "✅ 건전한 상승 — 가격 상승 + 거래량 증가. 추세 신뢰 가능",
    "none": "— 뚜렷한 신호 없음",
}


def _trend_pct(values):
    """최소자승 기울기를 기간 전체 변화율(%)로 정규화."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    if mean == 0:
        return 0.0
    xs = range(n)
    x_mean = (n - 1) / 2
    denom = sum((x - x_mean) ** 2 for x in xs)
    slope = sum((x - x_mean) * (y - mean) for x, y in zip(xs, values)) / denom
    return slope * (n - 1) / mean * 100


def detect(rows, window: int = 15):
    """일별 시세 rows([{close, volume}, ...] 과거→최신 순)에서 다이버전스 판정.

    거래량 데이터가 부족하면 None을 반환한다 (환율·금리 등).
    """
    usable = [r for r in rows if r.get("volume") and r["volume"] > 0]
    if len(usable) < window:
        return None
    recent = usable[-window:]

    price_trend = _trend_pct([r["close"] for r in recent])
    vol_trend = _trend_pct([r["volume"] for r in recent])

    price_up = price_trend >= PRICE_TREND_PCT
    price_down = price_trend <= -PRICE_TREND_PCT
    vol_up = vol_trend >= VOLUME_TREND_PCT
    vol_down = vol_trend <= -VOLUME_TREND_PCT

    if price_up and vol_down:
        signal = "bearish_divergence"
    elif price_down and vol_down:
        signal = "seller_exhaustion"
    elif price_down and vol_up:
        signal = "distribution"
    elif price_up and vol_up:
        signal = "healthy_uptrend"
    else:
        signal = "none"

    return {
        "signal": signal,
        "label": SIGNALS[signal],
        "price_trend_pct": round(price_trend, 2),
        "volume_trend_pct": round(vol_trend, 2),
        "window": window,
    }
