"""기술적 지표 계산 — RSI, 국소 고점/저점."""


def rsi_series(closes, period: int = 14):
    """Wilder 방식 RSI. closes와 같은 길이의 리스트 반환 (계산 불가 구간은 None)."""
    n = len(closes)
    out = [None] * n
    if n < period + 1:
        return out

    gains, losses = [], []
    for i in range(1, n):
        chg = closes[i] - closes[i - 1]
        gains.append(max(chg, 0.0))
        losses.append(max(-chg, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def _rsi(g, l):
        if l == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + g / l)

    out[period] = _rsi(avg_gain, avg_loss)
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = _rsi(avg_gain, avg_loss)
    return out


def local_maxima(values, order: int = 3):
    """양옆 order개보다 큰 국소 고점 인덱스 목록."""
    idx = []
    for i in range(order, len(values) - order):
        window = values[i - order:i + order + 1]
        if values[i] == max(window) and window.count(values[i]) == 1:
            idx.append(i)
    return idx


def local_minima(values, order: int = 3):
    """양옆 order개보다 작은 국소 저점 인덱스 목록."""
    idx = []
    for i in range(order, len(values) - order):
        window = values[i - order:i + order + 1]
        if values[i] == min(window) and window.count(values[i]) == 1:
            idx.append(i)
    return idx


def trend_pct(values):
    """최소자승 기울기를 기간 전체 변화율(%)로 정규화."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    if mean == 0:
        return 0.0
    x_mean = (n - 1) / 2
    denom = sum((x - x_mean) ** 2 for x in range(n))
    slope = sum((x - x_mean) * (y - mean) for x, y in enumerate(values)) / denom
    return slope * (n - 1) / mean * 100
