"""동적 클러스터 — 오늘 '같이 움직인' 종목군을 상관관계로 자동 감지.

theme_breadth가 '내가 미리 정의한 바스켓'을 보는 것과 달리, 이 신호는 바스켓을
사전에 정의하지 않는다. 시장이 그날그날 새로 묶어내는 그룹(테마 로테이션·
새로운 내러티브)을 놓치지 않으려면 정의가 아니라 데이터에서 그룹이 나와야 한다.

방법: 오늘 유의미하게 움직인 종목만 후보로 잡고, 최근 N일 일간수익률의
쌍별 상관이 임계값을 넘으면 같은 그룹으로 잇는다(union-find). 결과 그룹은
'시장이 오늘 한 덩어리로 취급한 종목들'이다. 이름은 붙이지 않는다 —
그 해석(무슨 테마인지·왜 묶였는지)은 분석 단계에서 뉴스와 대조해 하게 한다.
"""
TITLE = "동적 클러스터 — 오늘 같이 움직인 종목군 (자동 감지)"

CORR_WINDOW = 20      # 상관 계산 거래일
MIN_MOVE_PCT = 1.5    # 오늘 이만큼(절대값) 움직인 종목만 후보
CORR_THRESHOLD = 0.55  # 이 이상 상관이면 같은 그룹으로 연결
MIN_CLUSTER = 3       # 이 미만 그룹은 보고하지 않음
MAX_REPORT = 4        # 보고할 그룹 수 상한


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


def _today_move(rows):
    if len(rows) >= 2 and rows[-2].get("close"):
        return (rows[-1]["close"] - rows[-2]["close"]) / rows[-2]["close"] * 100
    return None


MIN_PAIR_DAYS = 8     # 쌍별 상관에 필요한 최소 공통 거래일


def _pair_returns(ca, cb):
    """두 종목의 '쌍별 공통 거래일'로 만든 수익률 쌍.

    전체 교집합을 쓰면 신규상장 한 종목 때문에 표본이 통째로 짧아진다.
    쌍마다 겹치는 날짜만 쓰면 이력이 긴 종목끼리는 온전히 비교된다."""
    common = sorted(set(ca) & set(cb))[-(CORR_WINDOW + 1):]
    if len(common) < MIN_PAIR_DAYS:
        return None, None
    ra, rb = [], []
    for i in range(1, len(common)):
        pa0, pa1 = ca[common[i - 1]], ca[common[i]]
        pb0, pb1 = cb[common[i - 1]], cb[common[i]]
        if pa0 and pb0:
            ra.append((pa1 - pa0) / pa0)
            rb.append((pb1 - pb0) / pb0)
    return ra, rb


class _DSU:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def find_clusters(ctx):
    """→ [ (심볼목록, 평균등락%, 평균상관) ] — 큰 그룹·강한 동조 순."""
    hist = ctx["histories"]
    moves, closes_by = {}, {}
    for sym, rows in hist.items():
        mv = _today_move(rows)
        if mv is None or abs(mv) < MIN_MOVE_PCT:
            continue
        if not any((r.get("volume") or 0) > 0 for r in rows):
            continue  # 금리·환율 등 비거래 자산 제외
        moves[sym] = mv
        closes_by[sym] = {r["date"]: r["close"] for r in rows if r.get("close")}
    if len(moves) < MIN_CLUSTER:
        return []

    # 1차 그룹 = '오늘 같은 방향으로 크게 움직인 종목들'. 상관이 낮아도 묶는다 —
    # 상관이 낮은데 오늘 같이 움직였다는 것 자체가 '새 그룹이 형성 중'이라는 신호다.
    out = []
    for direction in (-1, 1):
        members = sorted([s for s, m in moves.items() if (m < 0) == (direction < 0)],
                         key=lambda s: moves[s])
        if len(members) < MIN_CLUSTER:
            continue
        cs = []
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                ra, rb = _pair_returns(closes_by[members[i]], closes_by[members[j]])
                if not ra:
                    continue
                c = _corr(ra, rb)
                if c is not None:
                    cs.append(c)
        avg_move = sum(moves[m] for m in members) / len(members)
        avg_corr = sum(cs) / len(cs) if cs else 0.0
        out.append((members, avg_move, avg_corr))
    out.sort(key=lambda t: -abs(t[1]))
    return out[:MAX_REPORT]


def _kind(avg_corr):
    """평균 상관으로 그룹 성격 판별 — 새로 묶인 그룹이 오히려 중요한 신호."""
    if avg_corr >= CORR_THRESHOLD:
        return "기존 동조 그룹 (구조적 테마)"
    if avg_corr >= 0.35:
        return "동조 강화 중"
    return "🆕 새로 묶인 그룹 — 기존 상관이 낮은데 오늘 함께 움직임 (새 내러티브 형성 가능)"


def run(ctx):
    clusters = find_clusters(ctx)
    if not clusters:
        return None
    lines = [f"### {TITLE}",
             "(바스켓을 미리 정의하지 않고, 오늘 함께 크게 움직인 종목을 자동으로 묶었다. "
             f"평균 상관은 최근 {CORR_WINDOW}일 기준 — 낮은데 함께 움직였다면 '새 그룹 형성'이다. "
             "무슨 테마인지·왜 묶였는지는 뉴스와 대조해 해석할 것)"]
    for members, avg, corr in clusters:
        names = ", ".join(ctx["names"].get(m, m) for m in members)
        tone = "동반 하락" if avg < 0 else "동반 상승"
        mark = "🚨" if avg <= -2 else ("🟢" if avg >= 2 else "•")
        lines.append(f"- {mark} {len(members)}종목 {tone} 평균 {avg:+.1f}% "
                     f"(평균 상관 {corr:.2f} — {_kind(corr)})")
        lines.append(f"  · {names}")
    return "\n".join(lines)
