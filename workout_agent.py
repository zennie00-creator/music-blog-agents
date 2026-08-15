"""운동 데이터 분석 + 운동 일지 작성 (하루 여러 운동 지원).

Whoop의 객관적 숫자(강도·심박존·회복도)와 사용자가 직접 적은
주관적 느낌(운동 전후 기분·몸 상태)을 하나의 글로 엮는다.
하루에 여러 운동을 했으면 '오늘의 운동' 한 편으로 합쳐서 작성한다.
"""
import re

from core import writer

ZONE_LABELS = {
    "zone0": "존0(안정)",
    "zone1": "존1(가벼움)", "zone2": "존2(지방연소)", "zone3": "존3(유산소)",
    "zone4": "존4(고강도)", "zone5": "존5(최대)",
}

# 존별 색 (앱 내 막대 그래프용): 디자인 핸드오프의 세이지 그린 스텝.
# 안정(연한 크림그린)→최대(진한 세이지) 순.
ZONE_COLORS = {
    "zone0": "#e3e8da", "zone1": "#d7dfc9", "zone2": "#c1cfa9",
    "zone3": "#a9bf88", "zone4": "#8fac67", "zone5": "#5f7d51",
}


def zone_line(w):
    """존별 체류시간 한 줄 요약. 예: '존1 8분 · 존2 7분 · ...'"""
    zones = w.get("zones") or {}
    parts = [f"{ZONE_LABELS.get(k, k)} {v}분"
             for k, v in sorted(zones.items()) if v]
    return " · ".join(parts)


# 심박존 상세가 특히 의미 있는 유산소성 운동 키워드
_CARDIO_KEYS = (
    "러닝", "런닝", "달리", "조깅", "걷", "워킹", "산책", "하이킹", "등산",
    "트레킹", "사이클", "자전거", "스피닝", "수영", "로잉", "조정", "줄넘기",
    "인터벌", "트레드밀", "에어로빅", "일립티컬", "계단", "복싱", "댄스",
    "축구", "농구", "테니스", "배드민턴", "스쿼시",
    "run", "jog", "walk", "hik", "trek", "cycl", "spin", "swim", "row",
    "hiit", "cardio", "stair", "elliptical", "boxing", "dance",
    "soccer", "basket", "tennis",
)


def is_cardio(sport):
    s = (sport or "").lower()
    return any(k in s for k in _CARDIO_KEYS)


def zone_breakdown(w):
    """0이 아닌 존별 (존키, 라벨, 분, 비율%) 목록. 존 데이터 없으면 []."""
    zones = w.get("zones") or {}
    total = sum(v for v in zones.values() if v)
    if not total:
        return []
    return [(k, ZONE_LABELS.get(k, k), v, round(v / total * 100))
            for k, v in sorted(zones.items()) if v]


def _text_bar(pct, width=10):
    filled = min(width, max(1, round(pct / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def zone_text_block(w, indent=""):
    """붙여넣기 텍스트·Notion용 존별 체류시간 블록 (줄 목록).

    유산소 운동이면 존별 분·비율·막대를 줄마다 표기하고,
    그 외 운동은 기존처럼 한 줄 요약만 한다.
    """
    bd = zone_breakdown(w)
    if not bd:
        return []
    if not is_cardio(w.get("sport")):
        zl = zone_line(w)
        return [f"{indent}🫀 {zl}"] if zl else []
    lines = [f"{indent}🫀 심박존 체류시간"]
    for _k, label, mins, pct in bd:
        lines.append(f"{indent}{label} {mins}분 · {pct}%  {_text_bar(pct)}")
    return lines

# 종목명 키워드 → 이모지 (붙여넣기 텍스트 가독성용)
_SPORT_EMOJI = [
    (("러닝", "달리", "run"), "🏃"),
    (("걷", "워킹", "walk", "하이킹", "hik"), "🚶"),
    (("사이클", "자전거", "cycl", "스피닝", "spin"), "🚴"),
    (("수영", "swim"), "🏊"),
    (("웨이트", "근력", "역도", "lift", "strength"), "🏋️"),
    (("요가", "필라테스", "yoga", "pilates", "명상"), "🧘"),
    (("클라이밍", "climb"), "🧗"),
    (("테니스", "스쿼시", "배드민턴", "피클"), "🎾"),
    (("축구", "농구", "야구", "soccer", "basket"), "⚽"),
]


def sport_emoji(sport):
    s = (sport or "").lower()
    for keys, emoji in _SPORT_EMOJI:
        if any(k in s for k in keys):
            return emoji
    return "💪"


def workout_line(w):
    """붙여넣기 텍스트용 운동 한 줄 요약 (이모지 + 핵심 수치)."""
    parts = [f"{w.get('duration_min','?')}분"]
    dt = _distance_text(w)
    if dt:
        parts.append(dt)
    if w.get("strain") is not None:
        parts.append(f"Strain {w['strain']}")
    if w.get("avg_hr"):
        parts.append(f"평균 {w['avg_hr']}bpm")
    if w.get("kcal"):
        parts.append(f"{w['kcal']}kcal")
    return f"{sport_emoji(w.get('sport'))} {w.get('sport','운동')} · " + " · ".join(parts)


# ── 구간 기록(스플릿) ─────────────────────────────────────────────────
# Whoop API는 구간별 스플릿을 주지 않는다. 트레드밀처럼 본인이 정확히 기억하는
# 경우 직접 적게 해서, 코치가 워밍업/메인/쿨다운 구조까지 보고 분석하게 한다.
# 구간 기록 토큰 — 한 청크 안에서 위치 순서대로 읽는다. 대안 순서가 곧
# 우선순위다: 범위(7.2~9.0)를 먼저 잡아야 '-'가 두 숫자로 쪼개지지 않고,
# 속도(kmh)를 거리(km)보다 먼저 봐야 'kmh'의 km이 거리로 오인되지 않는다.
_SPLIT_TOKEN = re.compile(
    r"(?P<rlo>\d+(?:\.\d+)?)\s*(?:~|–|-|to|에서)\s*"
    r"(?P<rhi>\d+(?:\.\d+)?)\s*(?:kmh|kph)?"
    r"|(?P<time>\d+(?:\.\d+)?)\s*(?:분|min(?:s|utes)?)"
    r"|(?P<speed>\d+(?:\.\d+)?)\s*(?:kmh|kph)"
    r"|(?P<distkm>\d+(?:\.\d+)?)\s*km\b"
    r"|(?P<distm>\d+(?:\.\d+)?)\s*(?:m\b|미터)"
    r"|(?P<num>\d+(?:\.\d+)?)",
    re.I)


def parse_splits(text):
    """'2분 6.1 / 10분 8.6km/h' 같은 자유 입력을 구간 목록으로 파싱한다.

    반환: [{"minutes", "speed", "km", (선택) "speed_label"}, ...]

    v22의 '분+속도' 입력에 더해 (트레드밀 HIIT 실사용 요구):
    - 속도+거리: '10km/h 400m' → 시간을 거리/속도로 역산
    - 속도 범위: '7.2~9.0' '5.5 to 4.0' → 중간값으로 계산, 표기는 범위 그대로
    - 한 청크에 여러 구간: '10km/h 400m 7km/h 100m' → 두 구간으로
    분/속도 순서가 바뀌어도(6.1km/h 2분) 인식한다. 못 읽은 조각은 건너뛴다.
    """
    out = []
    # 'km/h'의 슬래시가 구간 구분자로 잘리지 않게 먼저 정규화한다
    norm = re.sub(r"km\s*/\s*h", "kmh", text or "", flags=re.I)
    for chunk in re.split(r"[\n,/·;]+", norm):
        if not chunk.strip():
            continue
        speed = None   # (값, 표기 라벨 또는 None)
        qty = None     # ("time", 분) 또는 ("dist", km)
        wild = None    # 단위 없는 숫자 — 다음 토큰이 역할을 정한다

        def emit():
            nonlocal speed, qty
            s, label = speed
            if qty[0] == "time":
                minutes, km = qty[1], s * qty[1] / 60
            else:
                km = qty[1]
                minutes = km / s * 60 if s else 0
            if s and minutes:
                seg = {"minutes": round(minutes, 2), "speed": round(s, 2),
                       "km": round(km, 3)}
                if label:
                    seg["speed_label"] = label
                if qty[0] == "dist":
                    # 적은 방식대로 표기하려고 기억한다 — 워밍업은 시간으로,
                    # 인터벌은 목표 거리로 달리는 게 실제 훈련 방식이라
                    # 전부 '분 @ 속도'로 통일하면 어색하다(사용자 피드백).
                    seg["by"] = "dist"
                out.append(seg)
            speed = qty = None

        for m in _SPLIT_TOKEN.finditer(chunk):
            if m.group("rlo"):
                a, b = float(m.group("rlo")), float(m.group("rhi"))
                # 라벨은 적은 표기 그대로 (9.0을 9로 뭉개지 않게)
                speed = ((a + b) / 2, f"{m.group('rlo')}~{m.group('rhi')}")
            elif m.group("time") is not None:
                qty = ("time", float(m.group("time")))
                if speed is None and wild is not None:
                    speed, wild = (wild, None), None
            elif m.group("speed") is not None:
                speed = (float(m.group("speed")), None)
            elif m.group("distkm") is not None:
                qty = ("dist", float(m.group("distkm")))
            elif m.group("distm") is not None:
                qty = ("dist", float(m.group("distm")) / 1000)
            else:  # 단위 없는 숫자
                n = float(m.group("num"))
                if qty is not None and speed is None:
                    speed = (n, None)        # '2분 6.1' — 남은 숫자는 속도
                elif speed is not None and qty is None:
                    qty = ("time", n)        # '8.5km/h 5' — 남은 숫자는 분
                elif wild is None:
                    wild = n                 # '6.1 2분' — 다음 토큰이 정함
                else:
                    # 숫자 두 개뿐이면 v22 규칙대로 '분 속도' 순서로 가정
                    speed, qty, wild = (n, None), ("time", wild), None
            if speed is not None and qty is not None:
                emit()
    return out


def splits_total_km(splits):
    return round(sum(s["km"] for s in (splits or [])), 2)


def splits_total_min(splits):
    return round(sum(s["minutes"] for s in (splits or [])), 1)


def fmt_minutes(minutes):
    """소수점 분을 사람이 읽는 시간으로: 0.86분 → '52초', 2.4분 → '2분 24초'."""
    total_sec = int(round(minutes * 60))
    m, sec = divmod(total_sec, 60)
    if m and sec:
        return f"{m}분 {sec}초"
    return f"{m}분" if m else f"{sec}초"


def split_line(s):
    """구간 한 줄 표기 — 적은 방식대로. 시간으로 달린 구간은 시간 먼저,
    거리로 달린 구간(인터벌)은 거리 먼저. ('by' 없는 옛 기록은 시간 취급)"""
    label = s.get("speed_label") or f"{s['speed']:g}"
    if s.get("by") == "dist":
        km = s["km"]
        dist = f"{km * 1000:g}m" if km < 1 else f"{km:g}km"
        return f"{dist} @ {label} km/h · {fmt_minutes(s['minutes'])}"
    return f"{fmt_minutes(s['minutes'])} @ {label} km/h · {s['km']:.2f} km"


def splits_lines(splits):
    """구간 기록을 요약·발행용 줄 목록으로."""
    if not splits:
        return []
    lines = ["🏃 구간 기록 (직접 입력 — 정확한 기록)"]
    lines += [split_line(s) for s in splits]
    lines.append(f"합계: {fmt_minutes(splits_total_min(splits))} · "
                 f"{splits_total_km(splits):.2f} km")
    return lines


def _distance_text(w):
    """편집된 운동의 거리 표기. distance_source: gps|manual|none."""
    src = w.get("distance_source", "gps")
    km = w.get("distance_km")
    if src == "none" or not km:
        return None
    if src == "manual":
        return f"{km} km (직접 입력)"
    return f"{km} km"


def _one_workout_lines(w, idx=None, total=1):
    lines = []
    head = f"[운동 {idx}] " if (idx and total > 1) else ""
    lines.append(f"{head}{w.get('sport', '운동')}"
                 + (f" · {w['local_time']}" if w.get("local_time") else ""))

    # '- '로 시작하면 st.markdown이 목록으로 바꿔 줄 간격이 벌어지므로 '·' 사용
    def add(label, value, unit=""):
        if value not in (None, ""):
            lines.append(f"· {label}: {value}{unit}")

    add("운동 시간", w.get("duration_min"), "분")
    dt = _distance_text(w)
    if dt:
        lines.append(f"· 거리: {dt}")
    add("Strain(강도, 0~21)", w.get("strain"))
    add("평균 심박수", w.get("avg_hr"), " bpm")
    add("최대 심박수", w.get("max_hr"), " bpm")
    add("소모 칼로리", w.get("kcal"), " kcal")
    add("고도 상승", w.get("altitude_gain_m"), " m")

    zones = w.get("zones") or {}
    if zones:
        z = ", ".join(f"{ZONE_LABELS.get(k, k)} {v}분"
                      for k, v in sorted(zones.items()) if v)
        if z:
            lines.append(f"· 심박존 분포: {z}")
    # 구간 기록은 본인이 정확히 기억해 적은 값 — 코치가 구조까지 보게 넘긴다
    sp = w.get("splits")
    if sp:
        lines.append("· 구간 기록 (본인이 직접 기록 — 정확함):")
        for s in sp:
            lines.append(f"   {s['minutes']:g}분 @ {s['speed']:g} km/h "
                         f"({s['km']:.2f} km)")
    return lines


def format_summary(workouts, recovery=None, cycle=None):
    """운동(들) + 회복/누적 데이터를 사람이 읽기 좋은 요약 텍스트로."""
    lines = []
    total = len(workouts)
    if total > 1:
        lines.append(f"오늘 총 {total}개의 운동을 했습니다.\n")
    for i, w in enumerate(workouts, 1):
        lines += _one_workout_lines(w, i, total)
        lines.append("")
    rec = []
    if cycle and cycle.get("day_strain") is not None:
        rec.append(f"오늘 누적 Strain: {cycle['day_strain']}"
                   f" ({cycle.get('as_of', '')} 집계 기준 — Whoop 공식 하루 누적치로,"
                   f" 활동별 Strain의 단순 합산과 다름)")
    if recovery:
        if recovery.get("recovery") is not None:
            rec.append(f"전일 회복도: {recovery['recovery']}%")
        if recovery.get("resting_hr"):
            rec.append(f"안정시 심박수: {recovery['resting_hr']} bpm")
        if recovery.get("hrv"):
            rec.append(f"HRV: {recovery['hrv']} ms")
    if rec:
        lines.append("[오늘 컨디션] " + " / ".join(rec))
    return "\n".join(lines).strip()


def stat_rows(workouts, recovery=None, cycle=None):
    """네이버 HTML 통계 카드용 (label, value) 목록.

    Strain은 활동별 합산이 하루 누적과 다르므로(로그 스케일),
    cycle의 Day Strain이 있으면 그것을 집계 시각과 함께 쓴다.
    """
    rows = []
    total_min = sum(w.get("duration_min") or 0 for w in workouts)
    total_kcal = sum(w.get("kcal") or 0 for w in workouts)
    strains = [w["strain"] for w in workouts if w.get("strain") is not None]
    max_hrs = [w["max_hr"] for w in workouts if w.get("max_hr")]
    total_km = 0.0
    for w in workouts:
        if w.get("distance_source") != "none" and w.get("distance_km"):
            total_km += w["distance_km"]

    if len(workouts) > 1:
        rows.append(("운동 수", f"{len(workouts)}개"))
    if total_min:
        rows.append(("총 시간", f"{total_min}분"))
    if cycle and cycle.get("day_strain") is not None:
        as_of = cycle.get("as_of", "")
        label = f"누적 Strain ({as_of} 기준)" if as_of else "누적 Strain"
        rows.append((label, cycle["day_strain"]))
    elif strains:
        label = "최고 Strain" if len(workouts) > 1 else "Strain"
        rows.append((label, max(strains)))
    if total_km:
        rows.append(("거리", f"{round(total_km, 2)} km"))
    if total_kcal:
        rows.append(("칼로리", f"{total_kcal} kcal"))
    if max_hrs:
        rows.append(("최대 심박", f"{max(max_hrs)} bpm"))
    if recovery and recovery.get("recovery") is not None:
        rows.append(("전일 회복도", f"{recovery['recovery']}%"))
    return rows


def analyze_workout(summary, profile=None, trend="", user_note="", whoop_note="",
                    coach_log=""):
    """코치 관점에서 오늘 운동(들)을 해석한다 (초안).

    trend      : 최근 2주 운동·회복 숫자 요약 (whoop_agent.get_trend_summary).
    user_note  : 운동한 사람이 코치에게 직접 전한 추가 정보/정정
                 (예: 명상 습관, 회복도 급락 원인). 데이터보다 우선한다.
    whoop_note : Whoop 앱 코치가 한 말 (사용자가 붙여넣음). 동료 코치의
                 의견으로 참고 — 반복하지 말고 보완한다.
    coach_log  : 지난 며칠간의 코치 로그 압축 요약 (format_coach_log). 이전
                 대화를 이어가듯 "지난번에 이렇게 얘기했었죠" 식으로 참고한다.
    """
    goal = (profile or {}).get("goals", "")
    goal_line = f"이 사람의 운동 목표: {goal}" if goal else ""
    notes = (profile or {}).get("notes", "")
    if notes:
        goal_line += f"\n이 사람에 대한 참고사항: {notes}"
    # 코치 답장에서 축적된 '지속적으로 알려진 사실'(명상 습관·무릎 주의 등)
    memory = ((profile or {}).get("coach_memory") or "").strip()
    if memory:
        goal_line += ("\n이 사람에 대해 지금까지 알게 된 지속적 사실 "
                      "(이미 반영해서 조언할 것):\n" + memory)
    trend_block = ""
    if trend:
        trend_block = f"""
[최근 운동·회복 추세 — 모든 수치에 날짜(요일)가 붙어 있음]
{trend}

추세 해석 규칙 (반드시 지킬 것):
- 날짜·요일과 수치는 위 블록에 적힌 것만 언급하세요. 블록에 없는 특정 날짜/요일의
  수치를 추측하거나 지어내는 것은 절대 금지입니다. 확실하지 않으면 날짜를 빼고 말하세요.
- 회복도·HRV는 하루하루의 등락보다 주간 평균과 몇 주에 걸친 흐름으로 해석하세요.
"""
    note_block = ""
    if user_note and user_note.strip():
        note_block = f"""
[운동한 사람이 코치인 당신에게 직접 전한 말 — 반드시 반영]
{user_note.strip()}

위 내용은 데이터에 없는 사실이므로 데이터 해석보다 우선하세요.
이전에 했을 법한 잘못된 가정(예: 안 하고 있는 습관을 권하기)을 바로잡고,
본인이 알려준 사실을 존중해서 조언하세요. 이미 하고 있는 것을 새로 시작하라고
권하지 마세요.
"""
    whoop_block = ""
    if whoop_note and whoop_note.strip():
        whoop_block = f"""
[Whoop 앱 코치의 코멘트 — 동료 코치 의견으로 참고]
{whoop_note.strip()}

같은 말을 반복하지 말고, 동의하면 짧게 언급만 하고 보완하거나
다른 관점(심박존·추세·오늘의 선택)을 더해주세요.
"""
    log_block = ""
    if coach_log and coach_log.strip():
        log_block = f"""
[지난 며칠간 우리가 나눈 코치 로그 — 이 대화의 연속선]
{coach_log.strip()}

위는 지난 일지들에서 당신이 이미 해준 조언과 그 사람의 답장입니다.
매번 처음 만난 것처럼 굴지 말고, 이 흐름을 이어서 말하세요.
지난번에 권한 것을 지켰는지/어떻게 됐는지 자연스럽게 짚어주되,
같은 조언을 토씨까지 반복하지는 마세요.
"""
    prompt = f"""당신은 이 사람을 꾸준히 지켜봐 온 퍼스널 트레이너이자 운동 코치입니다.
아래는 오늘 한 사람의 Whoop 운동 기록입니다. (여러 운동일 수 있습니다)

{summary}
{trend_block}{log_block}{note_block}{whoop_block}
{goal_line}

이 데이터를 2~3문단으로 해석해주세요:
1. 오늘 운동의 강도·심박존 분포가 의미하는 것 (쉬운 말로)
2. 최근 추세와 비교해 오늘 운동이 어떤 의미인지 — 훈련량이 늘었는지/줄었는지,
   회복도 흐름을 볼 때 잘한 선택이었는지 (추세 데이터가 있을 때만)
3. 다음 운동을 위한 짧은 조언
여러 운동을 했다면 하루 전체 흐름으로 엮어서 봐주세요.

말투 규칙:
- 숫자를 단순 나열하지 말고, 오래 함께해 온 코치가 카톡으로 보내주는 메시지처럼
  편하게 풀어주세요.
- 뻔한 칭찬("정말 대단하세요!", "훌륭합니다!")을 남발하지 말고, 잘한 점은
  구체적인 근거를 들어 한 번만 짚어주세요.
- "~하시길 바랍니다", "~하시는 것을 추천드립니다" 같은 격식체를 반복하지 말고
  "~해보세요", "~하면 좋겠어요" 정도로 자연스럽게."""
    return writer.generate(prompt, model=writer.QUICK_MODEL, max_tokens=1200)


# 일지에서 'AI가 쓴 티'를 걷어내는 문체 규칙.
# 초안 작성(write_workout_blog)과 다듬기(naturalize)가 함께 쓴다.
STYLE_RULES = """[문체 규칙 — 사람이 직접 쓴 일기처럼]
- 남에게 보여주기 전에 나 스스로 남기는 기록입니다. 잘 쓰려고 애쓴 티가 나면 안 됩니다.
- 기본은 '~했다'체 혼잣말 일기. 독자에게 말 걸듯 존댓말("~했어요", "~해보세요")을 쓰지 마세요.
- 내가 적어둔 기분·몸 상태 메모의 단어와 말투를 최대한 그대로 살리세요.
  매끈한 문어체로 고쳐 옮기지 말고, 그 표현을 뼈대로 앞뒤를 이어붙이세요.
- 문장 길이에 변화를 주세요. 툭 끊어지는 짧은 문장이 섞여야 자연스럽습니다.
- 숫자는 본문에 한두 개만, 이야기에 필요할 때 녹이세요. 수치 나열은 데이터 요약이 이미 합니다.
- 다음 같은 상투적 표현 금지: "값진/소중한 시간", "한 걸음 더 나아가", "몸이 보내는 신호",
  "~하는 나 자신을 발견했다", "여정", "완벽한 마무리", "그렇게 오늘도", "~가 아닐 수 없다".
- 모든 문단을 교훈이나 다짐으로 끝내지 마세요. 느낌만 적고 끝나는 문단이 있어도 됩니다.
- 감탄·과장("정말", "너무나", 느낌표)을 남발하지 말고 담백하게. 비유는 글 전체에 많아야 한 번.
- 내가 메모에 쓰지 않은 사실·추측·해석을 지어내지 마세요. "이건 처음인 듯하다",
  "회복돼서 다르게 소화됐다" 같은 추정·비교는 내가 직접 적었을 때만 씁니다.
  없는 인과·판단을 넣지 말고, 데이터에 실제로 있는 것만 담담히 적으세요.
- 코치가 한 말을 이 글에 옮기지 마세요. "코치한테 들었다", "~라고 했다" 식으로
  코치 조언을 인용·요약하지 마세요. 코치의 한마디는 이 글과 별개 영역에 따로 실립니다.
  이 글은 오로지 '내가 한 운동과 내가 느낀 것'만 담습니다."""


def write_workout_blog(summary, analysis, before, body, after, profile=None,
                       n_workouts=1):
    """데이터 + 나의 주관적 느낌을 하나의 운동 일지로 엮는다.

    analysis(코치 분석)는 더 이상 본문에 섞지 않는다 — 코치의 한마디는 별도
    영역에 실리고, 사용자는 일지에 코치 말을 인용하지 않기 때문. (호출부 호환을
    위해 인자는 유지하되 프롬프트에는 넣지 않는다.)
    """
    tone = (profile or {}).get("tone", "")
    tone_line = f"원하는 글 톤: {tone} (아래 문체 규칙과 충돌하면 이 톤을 우선)" if tone else ""
    style_mem = ((profile or {}).get("style_memory") or "").strip()
    style_block = ""
    if style_mem:
        style_block = f"""
[이전 일지들을 쓰며 내가 요청했던 문체 취향 — 꼭 반영]
{style_mem}
"""

    if n_workouts > 1:
        structure = (
            "오늘은 여러 운동을 했다. 각 운동을 이모지 소제목(예: '🏃 러닝', "
            "'🏋️ 웨이트 트레이닝')으로 구분해 섹션을 나눠 쓰되, 각 섹션에는 그때의 "
            "느낌을 중심으로 데이터를 한두 개만 녹이세요. 소제목은 이모지와 이름만 "
            "한 줄에 적으세요 — 마크다운 기호(#, ##, **)는 절대 쓰지 마세요. "
            "글 맨 위에 '오늘의 운동' 같은 전체 제목도 쓰지 마세요 (제목은 따로 "
            "붙습니다). 마지막에 하루를 돌아보는 짧은 문단 하나로 끝내세요.")
    else:
        structure = (
            "소제목 없이 일기체로 자연스럽게 이어서 쓰세요.")

    prompt = f"""당신은 오늘 이 운동을 직접 한 사람입니다. 블로거가 아니라,
운동을 마치고 책상에 앉아 오늘을 남겨두려고 일기를 쓰는 사람입니다.
아래 재료로 '오늘의 운동' 일지 한 편을 쓰세요.

[오늘의 운동 데이터]
{summary}

[운동 전 내가 적은 메모]
{before or '(기록 없음)'}

[운동 중·후 몸 상태 메모]
{body or '(기록 없음)'}

[운동 후 내가 적은 메모]
{after or '(기록 없음)'}

{tone_line}
{style_block}
{STYLE_RULES}

600~900자. {structure}
마무리는 내일 하고 싶은 것이나 스스로에게 하는 말을 한 줄로 툭 던지듯.
비장한 다짐, 명언투, 억지 감동은 금지."""
    return clean_blog_text(writer.generate(prompt, max_tokens=1800))


def clean_blog_text(text):
    """일지 본문에서 마크다운 서식 기호를 걷어낸다.

    화면·네이버 붙여넣기·Notion 모두 순수 텍스트를 기대하는데,
    모델이 가끔 '## 오늘의 운동', '### 🏃 러닝', '**강조**'처럼
    마크다운을 넣어 기호가 그대로 노출되는 것을 방지한다.
    """
    lines = []
    for line in (text or "").splitlines():
        lines.append(re.sub(r"^\s{0,3}#{1,6}\s*", "", line))
    text = "\n".join(lines).replace("**", "")
    # 첫 줄이 '오늘의 운동' 류의 중복 제목이면 제거 (제목은 출력물에 따로 붙는다)
    parts = text.strip().splitlines()
    if parts and parts[0].strip() in ("오늘의 운동", "오늘의 운동 일지", "운동 일지"):
        parts = parts[1:]
    return "\n".join(parts).strip()


def update_style_memory(existing, feedbacks):
    """이번 세션의 수정 요청들에서 '다음에도 적용할 문체 취향'만 추려
    기존 기억과 합친다. 결과는 짧은 목록(최대 8줄, 400자 이내)으로 유지해
    다음 일지 프롬프트에 넣어도 토큰 부담이 없게 한다."""
    fb = "\n".join(f"- {f}" for f in feedbacks)
    prompt = f"""운동 일지 초안을 받아본 사용자가 이번에 요청한 수정 사항들입니다:
{fb}

[지금까지 기억해 둔 문체 취향]
{existing.strip() or '(아직 없음)'}

위 수정 요청 중 '이번 글에만 해당하는 것'(특정 문장 교체, 오늘 데이터 정정 등)은
버리고, '다음 일지에도 계속 적용할 만한 문체·구성 취향'만 뽑아
기존 기억과 합친 최종 목록을 만들어주세요.

규칙:
- 겹치거나 모순되면 최신 요청을 우선해 하나로 정리
- 최대 8줄, 한 줄에 하나씩 "- "로 시작하는 간결한 규칙, 전체 400자 이내
- 새로 뽑을 게 없으면 기존 기억을 그대로 출력
- 기억도 없고 새로 뽑을 것도 없으면 아무것도 출력하지 마세요
- 목록 외의 설명·인사는 출력 금지"""
    return writer.generate(prompt, model=writer.QUICK_MODEL, max_tokens=500).strip()


def update_coach_memory(existing, notes):
    """코치에게 답장한 내용에서 '다음에도 계속 참일 사실'만 추려 기존 기억과 합친다.

    문체 취향(update_style_memory)과 달리, 이건 코치가 조언할 때 알아야 할
    '지속적 사실·습관·주의사항'(예: 명상 매일 15~20분, 오른쪽 무릎 주의,
    VO2Max 42)을 축적한다. 새 세션(다음 날)에도 프로필로 남아 분석에 반영된다.
    결과는 짧은 목록(최대 8줄, 400자 이내)으로 유지해 토큰 부담을 없앤다."""
    if not (notes or "").strip():
        return (existing or "").strip()
    prompt = f"""아래는 운동하는 사람이 자기 코치에게 직접 전한 말들입니다:
{notes.strip()}

[지금까지 코치가 기억해 둔 이 사람에 대한 지속적 사실]
{(existing or '').strip() or '(아직 없음)'}

위 말들 중 '오늘 하루에만 해당하는 것'(예: 오늘 회식으로 회복도 급락)은 버리고,
'앞으로도 계속 참일 사실·습관·몸 상태·주의사항'(예: 명상을 매일 한다,
오른쪽 무릎이 약하다, VO2Max 42)만 뽑아 기존 기억과 합친 최종 목록을 만드세요.

규칙:
- 겹치거나 모순되면 최신 정보를 우선해 하나로 정리
- 최대 8줄, 한 줄에 하나씩 "- "로 시작하는 간결한 사실, 전체 400자 이내
- 새로 뽑을 게 없으면 기존 기억을 그대로 출력
- 기억도 없고 새로 뽑을 것도 없으면 아무것도 출력하지 마세요
- 목록 외의 설명·인사는 출력 금지"""
    return writer.generate(prompt, model=writer.QUICK_MODEL, max_tokens=500).strip()


def format_coach_log(logs, limit=5):
    """코치 로그(최신순 dict 목록)를 프롬프트용 압축 텍스트로. (LLM 비용 없음)

    각 항목: {date, sports, analysis, reply}. 토큰을 아끼려고 분석은 앞부분만,
    답장은 짧게 잘라 '날짜 · 종목 · 그때 조언 요지 · 내 답장'으로만 남긴다.
    최신 limit개만, 오래된 것이 위로 오도록(대화 흐름 순) 정렬해 돌려준다.
    """
    if not logs:
        return ""
    recent = logs[:limit]
    lines = []
    for e in reversed(recent):  # 오래된 것 → 최신 순 (대화처럼 읽히게)
        date = e.get("date", "")
        sports = e.get("sports", "")
        head = f"[{date} · {sports}]" if sports else f"[{date}]"
        lines.append(head)
        analysis = (e.get("analysis") or "").strip().replace("\n", " ")
        if analysis:
            lines.append(f"  코치: {analysis[:220]}")
        reply = (e.get("reply") or "").strip().replace("\n", " ")
        if reply:
            lines.append(f"  본인 답장: {reply[:160]}")
    return "\n".join(lines)


def naturalize(text):
    """이미 쓴 일지에서 'AI가 쓴 티'가 나는 문체만 걷어낸다. 내용·구조는 유지."""
    prompt = f"""아래 운동 일지에서 기계가 쓴 티가 나는 문체만 걷어내고,
사람이 직접 쓴 일기처럼 자연스럽게 다듬어주세요.
사실·내용·구조·분량은 그대로 두고 문장만 손보세요.

{STYLE_RULES}

[일지 원문]
{text}

다듬은 전체 본문만 출력하세요. 설명·인사·머리말 금지."""
    return clean_blog_text(writer.generate(prompt, max_tokens=max(2000, len(text) + 500)))
