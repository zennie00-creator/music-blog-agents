"""동적 클러스터 — 오늘 '같이 움직인' 종목군을 상관관계로 자동 감지.

theme_breadth가 '내가 미리 정의한 바스켓'을 보는 것과 달리, 이 신호는 바스켓을
사전에 정의하지 않는다. 시장이 그날그날 새로 묶어내는 그룹(테마 로테이션·
새로운 내러티브)을 놓치지 않으려면 정의가 아니라 데이터에서 그룹이 나와야 한다.

방법: 오늘 유의미하게 움직인 종목만 후보로 잡고, 최근 N일 일간수익률의
쌍별 상관이 임계값을 넘으면 같은 그룹으로 잇는다(union-find). 결과 그룹은
'시장이 오늘 한 덩어리로 취급한 종목들'이다. 이름은 붙이지 않는다 —
그 해석(무슨 테마인지·왜 묶였는지)은 분석 단계에서 뉴스와 대조해 하게 한다.
"""
import json
import os

from core import config

TITLE = "동적 클러스터 — 오늘 같이 움직인 종목군 (자동 감지)"

# 클러스터 구성 이력 — 어제와 무엇이 달라졌는지(합류·이탈·신규 그룹) 비교용.
# signal_log/는 Actions가 매일 커밋하므로 이력이 보존된다.
_STORE = os.path.join(config.ROOT_DIR, "signal_log", "clusters.jsonl")

CORR_WINDOW = 20      # 상관 계산 거래일
MIN_MOVE_PCT = 1.5    # 오늘 시장 대비 이만큼(%p) 초과로 움직인 종목만 후보
CORR_THRESHOLD = 0.5  # 이 이상이라야 '함께 움직인다'고 말한다 (미만은 묶지 않음)
STRONG_CORR = 0.7     # 강한 동조
MIN_CLUSTER = 3       # 이 미만 그룹은 보고하지 않음
MAX_REPORT = 4        # 보고할 그룹 수 상한

# 시장 기준(잔차 계산용). 지수 자체는 클러스터 대상이 아니다 —
# 지수는 개별 종목의 합이라 항상 같이 움직이고, 그건 '테마'가 아니다.
MARKET = "gsheet/INDEXSP:.INX"
_INDEX_TOKENS = ("INDEX", "KOSPI", "CURRENCY", "KRW")


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


def _pair_returns(ca, cb, cm=None):
    """두 종목의 '쌍별 공통 거래일'로 만든 수익률 쌍.

    cm(시장 종가)을 주면 시장 수익률을 뺀 잔차로 돌려준다. 시장 공통 요인을
    제거해야 '함께 움직인다'가 테마를 뜻하게 된다 — 시장이 다 오른 날의
    동반 상승은 관계가 아니라 베타다 (엔비디아·마이크론 원상관 0.44 →
    잔차 0.27처럼, 원상관은 관계를 과장한다).

    전체 교집합 대신 쌍별 공통 날짜를 쓰므로 신규상장 종목이 표본을 깎지 않는다."""
    keys = set(ca) & set(cb)
    if cm is not None:
        keys &= set(cm)
    common = sorted(keys)[-(CORR_WINDOW + 1):]
    if len(common) < MIN_PAIR_DAYS:
        return None, None
    ra, rb = [], []
    for i in range(1, len(common)):
        pa0, pa1 = ca[common[i - 1]], ca[common[i]]
        pb0, pb1 = cb[common[i - 1]], cb[common[i]]
        if not (pa0 and pb0):
            continue
        x, y = (pa1 - pa0) / pa0, (pb1 - pb0) / pb0
        if cm is not None:
            m0, m1 = cm[common[i - 1]], cm[common[i]]
            if not m0:
                continue
            mr = (m1 - m0) / m0
            x, y = x - mr, y - mr
        ra.append(x)
        rb.append(y)
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


def _is_index(sym):
    up = sym.upper()
    return any(tok in up for tok in _INDEX_TOKENS)


def find_clusters(ctx):
    """→ [ (심볼목록, 평균 초과등락%p, 평균 잔차상관) ] — 강한 동조 순.

    '오늘 같은 방향'만으로 묶지 않는다. 시장 대비 초과로 움직였고(베타 제거),
    잔차 상관이 임계 이상인 쌍만 이어서(union-find) 실제 그룹을 만든다.
    상관이 임계 미만인 종목은 억지로 묶지 않고 그냥 제외한다."""
    hist = ctx["histories"]
    mkt_rows = hist.get(MARKET, [])
    cm = {r["date"]: r["close"] for r in mkt_rows if r.get("close")} or None
    mkt_move = _today_move(mkt_rows) or 0.0

    excess, closes_by = {}, {}
    for sym, rows in hist.items():
        if _is_index(sym):
            continue  # 지수는 종목의 합 — 테마가 아니다
        mv = _today_move(rows)
        if mv is None:
            continue
        if not any((r.get("volume") or 0) > 0 for r in rows):
            continue  # 금리·환율 등 비거래 자산 제외
        ex = mv - mkt_move  # 시장 대비 초과 이동(%p)
        if abs(ex) < MIN_MOVE_PCT:
            continue
        excess[sym] = ex
        closes_by[sym] = {r["date"]: r["close"] for r in rows if r.get("close")}
    if len(excess) < MIN_CLUSTER:
        return []

    syms = sorted(excess)
    dsu = _DSU(syms)
    pair_corr = {}
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            a, b = syms[i], syms[j]
            if (excess[a] < 0) != (excess[b] < 0):
                continue  # 오늘 반대로 움직였으면 같은 그룹일 수 없다
            ra, rb = _pair_returns(closes_by[a], closes_by[b], cm)
            if not ra:
                continue
            c = _corr(ra, rb)
            if c is not None and c >= CORR_THRESHOLD:
                dsu.union(a, b)
                pair_corr[(a, b)] = c

    groups = {}
    for s in syms:
        groups.setdefault(dsu.find(s), []).append(s)

    out = []
    for members in groups.values():
        if len(members) < MIN_CLUSTER:
            continue
        cs = [c for (a, b), c in pair_corr.items() if a in members and b in members]
        if not cs:
            continue
        members.sort(key=lambda s: excess[s])
        out.append((members, sum(excess[m] for m in members) / len(members),
                    sum(cs) / len(cs)))
    out.sort(key=lambda t: -t[2])
    return out[:MAX_REPORT]


def _kind(avg_corr):
    """묶인 그룹의 동조 강도. 임계 미만은 애초에 그룹이 되지 않는다."""
    if avg_corr >= STRONG_CORR:
        return "강한 동조, 사실상 한 몸으로 거래됨"
    return "뚜렷한 동조, 같은 재료에 반응"


def _today_of(ctx):
    dates = [rows[-1]["date"] for rows in ctx["histories"].values() if rows]
    return max(dates) if dates else ""


def _load_prev(today):
    """오늘 이전의 가장 최근 클러스터 스냅숏 → (날짜, {방향: [심볼]}). 없으면 (None, {})."""
    if not os.path.exists(_STORE):
        return None, {}
    best = None
    with open(_STORE, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if rec.get("date") and rec["date"] < today:
                if best is None or rec["date"] > best["date"]:
                    best = rec
    return (best["date"], best.get("groups", {})) if best else (None, {})


def _save(today, groups):
    """오늘 클러스터 구성을 저장 (같은 날짜는 덮어씀)."""
    lines = []
    if os.path.exists(_STORE):
        with open(_STORE, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    if json.loads(ln).get("date") == today:
                        continue
                except json.JSONDecodeError:
                    continue
                lines.append(ln)
    lines.append(json.dumps({"date": today, "groups": groups}, ensure_ascii=False))
    os.makedirs(os.path.dirname(_STORE), exist_ok=True)
    with open(_STORE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


PROMOTE_LOOKBACK = 10   # 최근 며칠을 볼지
PROMOTE_MIN_DAYS = 6    # 그 중 며칠 이상 함께 잡히면 '지속 그룹'으로 본다
PROMOTE_MIN_SIZE = 3


def promotion_candidates(ctx, today):
    """여러 날 반복해서 함께 묶인 핵심 멤버 → 정식 바스켓 승격 후보.

    하루치 클러스터는 그날의 사건일 수 있다. 최근 N일 중 M일 이상 계속 같이
    잡힌 종목들만 '구조적 그룹'으로 보고 제안한다. 자동 등록은 하지 않는다 —
    바스켓 등록은 코드 변경이고, 일시적 그룹이 굳어지면 오히려 해롭다."""
    from collections import Counter
    if not os.path.exists(_STORE):
        return []
    recs = []
    with open(_STORE, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if rec.get("date") and rec["date"] <= today:
                recs.append(rec)
    recs = sorted(recs, key=lambda r: r["date"])[-PROMOTE_LOOKBACK:]
    if len(recs) < PROMOTE_MIN_DAYS:
        return []

    # 이미 정식 바스켓에 있는 종목 조합은 제안하지 않는다
    try:
        from modes.investment.signals.theme_breadth import BASKETS
        known = [set(syms) for _, syms in BASKETS]
    except Exception:
        known = []

    out = []
    for key in ("down", "up"):
        cnt = Counter()
        for rec in recs:
            for s in rec.get("groups", {}).get(key, []):
                cnt[s] += 1
        core = sorted([s for s, c in cnt.items() if c >= PROMOTE_MIN_DAYS])
        if len(core) < PROMOTE_MIN_SIZE:
            continue
        cs = set(core)
        if any(cs <= k for k in known):
            continue  # 기존 바스켓의 부분집합 → 새로울 게 없다
        out.append((key, core, len(recs)))
    return out


def _change_note(ctx, prev_date, prev, cur):
    """어제 대비 구성 변화 코멘트. 변화가 없으면 None."""
    if not prev_date:
        return None
    notes = []
    for key, label in (("down", "하락 그룹"), ("up", "상승 그룹")):
        old, new = set(prev.get(key, [])), set(cur.get(key, []))
        if not new:
            if old:
                notes.append(f"{label} 해소")
            continue
        if not old:
            notes.append(f"{label} 신규 형성({len(new)}종목)")
            continue
        joined = [ctx["names"].get(s, s) for s in sorted(new - old)]
        left = [ctx["names"].get(s, s) for s in sorted(old - new)]
        if joined:
            notes.append(f"{label} 신규 합류: {', '.join(joined)}")
        if left:
            notes.append(f"{label} 이탈: {', '.join(left)}")
    if not notes:
        return None
    return f"- 🔄 전일({prev_date}) 대비 변화 — " + " / ".join(notes)


def run(ctx):
    clusters = find_clusters(ctx)
    if not clusters:
        return None
    lines = [f"### {TITLE}",
             "(바스켓을 미리 정의하지 않고 자동 감지. 시장(S&P) 대비 초과로 움직였고, "
             f"최근 {CORR_WINDOW}일 '시장 요인을 뺀 잔차' 상관이 {CORR_THRESHOLD} 이상인 "
             "종목만 묶는다 — 시장이 다 오른 날의 동반 상승은 관계가 아니라 베타이므로 제외된다. "
             "무슨 테마인지·왜 묶였는지는 뉴스와 대조해 해석할 것)"]
    cur = {}
    for members, avg, corr in clusters:
        names = ", ".join(ctx["names"].get(m, m) for m in members)
        tone = "동반 하락" if avg < 0 else "동반 상승"
        mark = "🚨" if avg <= -2 else ("🟢" if avg >= 2 else "•")
        lines.append(f"- {mark} {len(members)}종목 {tone} (시장 대비 평균 {avg:+.1f}%p, "
                     f"잔차상관 {corr:.2f} — {_kind(corr)})")
        lines.append(f"  · {names}")
        cur["down" if avg < 0 else "up"] = list(members)

    # 구성 변화(합류·이탈·신규 형성)는 그 자체가 신호 — 전일과 비교해 남긴다.
    today = _today_of(ctx)
    if today:
        try:
            prev_date, prev = _load_prev(today)
            note = _change_note(ctx, prev_date, prev, cur)
            if note:
                lines.append(note)
            _save(today, cur)
            # 며칠째 반복되는 조합은 정식 바스켓 후보로 제안 (등록은 사람이 결정)
            for key, core, days in promotion_candidates(ctx, today):
                names = ", ".join(ctx["names"].get(s, s) for s in core)
                tone = "하락" if key == "down" else "상승"
                lines.append(f"- 📌 바스켓 승격 후보 — 최근 {days}일 중 "
                             f"{PROMOTE_MIN_DAYS}일 이상 함께 {tone}한 {len(core)}종목: {names}")
        except Exception as e:
            print(f"  ⚠️ 클러스터 변화 비교 실패 (건너뜀): {e}")
    return "\n".join(lines)
