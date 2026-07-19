"""금리 커브 · 한미 금리차 신호.

투자 전제의 '금리 기둥'을 정량으로 뒷받침한다:
- 2s10s (미 10년-2년): 역전이면 침체 선행 경계, 역전 해소(재스티프닝)도 그 자체로 신호
- 10s30s (미 30년-10년): 장기 기대·수급 (재정 우려 시 스티프닝)
- 한미 10년 금리차: 역전 폭 확대는 자본 유출·원화 약세 압력

portfolio.md의 채권 심볼(stooq 형식 `{만기}usy.b` / `{만기}kry.b`)을 자동 인식한다.
"""
import re

TITLE = "금리 커브 · 한미 금리차"

_BOND = re.compile(r"^(\d+)(us|kr)y\.b$")
LOOKBACK = 20  # 20거래일 전 대비 변화


def _bond_yields(ctx):
    out = {}
    for sym, rows in ctx["histories"].items():
        m = _BOND.match(sym)
        if not m or len(rows) < 2:
            continue
        closes = [r["close"] for r in rows]
        ago = closes[-(LOOKBACK + 1)] if len(closes) > LOOKBACK else closes[0]
        out[(m.group(2), int(m.group(1)))] = {"now": closes[-1], "ago": ago}
    return out


def _spread_line(label, a, b, invert_warn, normal_note, invert_note):
    now = a["now"] - b["now"]
    ago = a["ago"] - b["ago"]
    direction = "확대" if now > ago else ("축소" if now < ago else "유지")
    note = invert_note if now < 0 else normal_note
    warn = " 🚨" if (now < 0 and invert_warn) else ""
    return (f"- {label}: {now:+.2f}%p (20일 전 {ago:+.2f}%p → {direction}){warn} — {note}")


def run(ctx):
    y = _bond_yields(ctx)
    if not y:
        return None
    lines = [f"### {TITLE}"]

    us2, us10, us30 = y.get(("us", 2)), y.get(("us", 10)), y.get(("us", 30))
    kr10 = y.get(("kr", 10))

    if us2 and us10:
        lines.append(_spread_line(
            "미 2s10s (10년-2년)", us10, us2, invert_warn=True,
            normal_note="정상 커브. 스티프닝 속도가 빠르면 인하 기대(경기 둔화) 확인 필요",
            invert_note="역전 상태 — 침체 선행 신호 경계. 역전 '해소' 국면이 역사적으로 더 위험",
        ))
    if us10 and us30:
        lines.append(_spread_line(
            "미 10s30s (30년-10년)", us30, us10, invert_warn=False,
            normal_note="장기 구간 정상. 급격한 스티프닝은 재정·수급 우려 반영",
            invert_note="장기 구간 역전 — 초장기 수요 쏠림",
        ))
    if kr10 and us10:
        lines.append(_spread_line(
            "한미 10년 금리차 (한국-미국)", kr10, us10, invert_warn=False,
            normal_note="한국 금리 우위",
            invert_note="역전 — 폭 확대 시 자본 유출·원화 약세 압력",
        ))

    if len(lines) == 1:
        lines.append("- (커브 계산에 필요한 만기 조합 부족)")
    return "\n".join(lines)
