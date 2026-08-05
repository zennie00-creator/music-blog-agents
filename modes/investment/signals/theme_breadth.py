"""테마 바스켓 — 종목군의 동반 이동·브레드스 감지.

개별 종목 신호로는 놓치기 쉬운 '테마가 통째로 움직이는' 국면
(예: 어젯밤 반도체 장비·메모리·엔비디아 동반 약세 = AI 하드웨어/순환투자
테마가 한꺼번에 눌림)을 바스켓 단위 평균 등락률·브레드스로 잡는다.

바스켓은 종목 그룹이라 섹션 이름에 의존하지 않고 심볼 리스트로 직접 정의한다.
"""
TITLE = "테마 바스켓 — 동반 이동·브레드스 (최근 1일)"

# (바스켓 이름, [심볼...]) — 심볼은 portfolio.md와 정확히 일치해야 한다.
BASKETS = [
    ("AI 하드웨어 (엔비디아 진영)", [
        "gsheet/NASDAQ:NVDA", "gsheet/NASDAQ:MU", "gsheet/NASDAQ:SKHY",
        "naver/000660", "gsheet/NYSE:COHR", "gsheet/NASDAQ:ASML",
        "gsheet/NASDAQ:AMAT", "gsheet/NASDAQ:LRCX", "gsheet/NASDAQ:KLAC",
    ]),
]

STRONG_PCT = 2.0   # 평균 등락 임계 (동반 강/약세 판정)
BREADTH_PCT = 70   # 동반 판정 브레드스 (%)
MIN_MEMBERS = 3    # 이 미만이면 바스켓 판정 보류


def _ret(rows):
    """최근 1일 등락률(%) — 2점 미만이면 None."""
    if len(rows) >= 2 and rows[-2]["close"]:
        return (rows[-1]["close"] - rows[-2]["close"]) / rows[-2]["close"] * 100
    return None


def basket_stats(ctx, syms):
    rets = []
    for s in syms:
        r = _ret(ctx["histories"].get(s, []))
        if r is not None:
            rets.append(r)
    if len(rets) < MIN_MEMBERS:
        return None
    n = len(rets)
    avg = sum(rets) / n
    down = sum(1 for r in rets if r < 0)
    up = sum(1 for r in rets if r > 0)
    if avg <= -STRONG_PCT and down / n * 100 >= BREADTH_PCT:
        label = f"🚨 테마 동반 약세 — 평균 {avg:+.1f}%, {down}/{n} 하락 (동반 매도)"
    elif avg >= STRONG_PCT and up / n * 100 >= BREADTH_PCT:
        label = f"🟢 테마 동반 강세 — 평균 {avg:+.1f}%, {up}/{n} 상승"
    elif down / n * 100 >= BREADTH_PCT:
        label = f"⚠️ 약세 우위 — 평균 {avg:+.1f}%, {down}/{n} 하락"
    elif up / n * 100 >= BREADTH_PCT:
        label = f"🙂 강세 우위 — 평균 {avg:+.1f}%, {up}/{n} 상승"
    else:
        label = f"➖ 혼조 — 평균 {avg:+.1f}%, {up}↑/{down}↓ (n={n})"
    return {"avg": avg, "n": n, "up": up, "down": down, "label": label}


def run(ctx):
    lines = [f"### {TITLE}"]
    found = False
    for name, syms in BASKETS:
        st = basket_stats(ctx, syms)
        if not st:
            continue
        found = True
        lines.append(f"- {name}: {st['label']}")
        # 어떤 종목으로 구성된 바스켓인지 명기 — 이름만 보고는 범위를 알 수 없다.
        # (이력이 없어 판정에서 빠진 종목은 표시하지 않는다)
        members = [ctx["names"].get(s, s) for s in syms
                   if _ret(ctx["histories"].get(s, [])) is not None]
        if members:
            lines.append(f"  · 구성({len(members)}): {', '.join(members)}")
    return "\n".join(lines) if found else None
