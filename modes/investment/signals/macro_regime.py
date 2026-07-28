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
        lines.append(f"- 에너지(WTI/USO) {ENERGY_WINDOW}거래일: {en:+.1f}%{flag}")

    return "\n".join(lines) if len(lines) > 1 else None
