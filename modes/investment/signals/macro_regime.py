"""매크로 국면 보드 — 시장 전체 헤드윈드를 우리 데이터로 정량화.

개별 종목 신호로는 안 잡히는 '국면' 논거(민너비니류: 계절성·4년 사이클·
금리-주식 역상관·에너지 급등·금리 수준)를 매일 계산해 한 보드로 모은다.
정밀 역사비교(37년/2008년/수십년)는 장기 데이터가 없어 못 하지만, '지금이
그 위험 구간인지'는 우리 이력으로 판정한다.
"""
from collections import defaultdict
from datetime import date

SPX = "gsheet/INDEXSP:.INX"
TNX = "gsheet/INDEXCBOE:TNX"
USO = "gsheet/NYSEARCA:USO"
SOX = "gsheet/INDEXNASDAQ:SOX"

TITLE = "매크로 국면 보드 (헤드윈드 점검)"

CORR_WINDOW = 30       # 금리-주식 상관 계산 거래일
ENERGY_WINDOW = 25     # ≈5주 (거래일)
ENERGY_SURGE_PCT = 15  # 에너지 급등 플래그 임계
CORR_STRONG = -0.4     # 강한 역상관 임계


def _corr(xs, ys):
    n = len(xs)
    if n < 5:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _cycle_year():
    """미 대통령(선거) 4년 사이클 위치. 2024=선거의 해 기준."""
    pos = (date.today().year - 2024) % 4
    return {
        0: "선거의 해",
        1: "1년차 (선거 다음해)",
        2: "2년차·중간선거해 (역사적으로 약한 구간)",
        3: "3년차 (역사적으로 강한 구간)",
    }[pos], pos


def _yield_equity_corr(ctx):
    sp = {r["date"]: r["close"] for r in ctx["histories"].get(SPX, []) if r.get("close")}
    tn = {r["date"]: r["close"] for r in ctx["histories"].get(TNX, []) if r.get("close")}
    common = sorted(set(sp) & set(tn))
    if len(common) < CORR_WINDOW + 1:
        return None
    common = common[-(CORR_WINDOW + 1):]
    dy, ret = [], []
    for i in range(1, len(common)):
        p0, p1 = sp[common[i - 1]], sp[common[i]]
        y0, y1 = tn[common[i - 1]], tn[common[i]]
        if p0:
            dy.append(y1 - y0)
            ret.append((p1 - p0) / p0)
    return _corr(dy, ret)


def _energy_5wk(ctx):
    rows = ctx["histories"].get(USO, [])
    if len(rows) < ENERGY_WINDOW + 1:
        return None
    a, b = rows[-ENERGY_WINDOW - 1]["close"], rows[-1]["close"]
    return (b - a) / a * 100 if a else None


def _yield_level(ctx):
    rows = [r["close"] for r in ctx["histories"].get(TNX, []) if r.get("close")]
    if len(rows) < 20:
        return None
    cur, hi = rows[-1], max(rows)
    return cur, hi, cur >= hi * 0.97


def _sox_yoy(ctx):
    """SOX 전년 대비(%) — 초과 유동성 선행지표가 예측한다는 '결과 변수'.
    유동성 게이지 자체(G10)는 유료 데이터라 못 받지만, 그 대상인 SOX YoY는
    우리 이력으로 직접 계산해 국면(둔화/가속)을 추적할 수 있다."""
    rows = [r for r in ctx["histories"].get(SOX, []) if r.get("close")]
    if len(rows) < 200:
        return None

    def _yoy_at(idx):
        """rows[idx] 시점의 전년 대비(%) — 1년 전 근처(±20일) 값이 있어야 계산."""
        cur = rows[idx]
        target = f"{int(cur['date'][:4]) - 1}{cur['date'][4:]}"
        prior = min(rows, key=lambda r: _date_gap(r["date"], target))
        if _date_gap(prior["date"], target) > 20 or not prior["close"]:
            return None
        return (cur["close"] / prior["close"] - 1) * 100

    yoy = _yoy_at(-1)
    if yoy is None:
        return None
    # 약 3개월 전 시점의 YoY와 비교해 가속/둔화 방향을 본다
    prev = _yoy_at(-63) if len(rows) > 63 else None
    trend = ""
    if prev is not None:
        trend = " 둔화 중" if yoy < prev else " 가속 중"
    return yoy, trend


def _date_gap(a, b):
    """YYYY-MM-DD 두 날짜의 대략적 일수 차이 (절대값)."""
    try:
        from datetime import date as _d
        da = _d.fromisoformat(a)
        db = _d.fromisoformat(b)
        return abs((da - db).days)
    except ValueError:
        return 10 ** 6


def _seasonality(ctx):
    """현재 '달'의 역사적 월간(MoM) 평균 수익률 — 우리 S&P 이력 기준(표본 작음)."""
    rows = ctx["histories"].get(SPX, [])
    if len(rows) < 60:
        return None
    monthly = {}
    for r in rows:
        if r.get("close"):
            monthly[r["date"][:7]] = r["close"]  # 정렬돼 있어 그 달 마지막 종가
    keys = sorted(monthly)
    by_mo = defaultdict(list)
    for i in range(1, len(keys)):
        p0, p1 = monthly[keys[i - 1]], monthly[keys[i]]
        if p0:
            by_mo[int(keys[i][5:7])].append((p1 - p0) / p0 * 100)
    cur = date.today().month
    vals = by_mo.get(cur)
    if not vals:
        return None
    return cur, sum(vals) / len(vals), len(vals)


def run(ctx):
    lines = [f"### {TITLE}"]

    label, _ = _cycle_year()
    lines.append(f"- 4년 사이클: {date.today().year}년 = {label}")

    seas = _seasonality(ctx)
    if seas:
        mo, avg, k = seas
        tone = "계절적 약세" if avg < 0 else "계절적 강세"
        lines.append(f"- 계절성: {mo}월 역사 평균 {avg:+.1f}% ({tone}, 표본 {k}년·짧음)")

    corr = _yield_equity_corr(ctx)
    if corr is not None:
        flag = " 🚩 금리 주도 장세(금리↑=주식↓)" if corr <= CORR_STRONG else ""
        lines.append(f"- 금리-주식 상관({CORR_WINDOW}일): {corr:+.2f}{flag}")

    yl = _yield_level(ctx)
    if yl:
        cur, hi, near = yl
        flag = " 🚩 고점권" if near else ""
        lines.append(f"- 10년물 금리: {cur:.2f}% (이력 내 고점 {hi:.2f}%){flag}")

    en = _energy_5wk(ctx)
    if en is not None:
        flag = " 🚩 급등(인플레·금리 상방)" if en >= ENERGY_SURGE_PCT else ""
        # USO는 WTI를 추종하는 ETF다. 배럴당 유가가 아니라 ETF 가격 변화율이므로
        # 'WTI 가격'으로 읽히지 않게 표기한다 (수준이 아니라 방향·변화율만 의미 있음).
        lines.append(f"- 에너지(원유 ETF USO, WTI 추종) {ENERGY_WINDOW}거래일 변화: {en:+.1f}%{flag}")

    sox = _sox_yoy(ctx)
    if sox:
        yoy, trend = sox
        # 초과 유동성 선행지표가 예측 대상으로 삼는 변수 — 유동성 국면 판단의 결과 지표
        lines.append(f"- 반도체(SOX) 전년 대비: {yoy:+.1f}%{trend} "
                     "(초과 유동성 선행지표의 대상 변수 — 유동성 역풍 가설의 검증점)")

    return "\n".join(lines) if len(lines) > 1 else None
