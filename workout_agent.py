"""운동 데이터 분석 + 운동 일지 작성 (하루 여러 운동 지원).

Whoop의 객관적 숫자(강도·심박존·회복도)와 사용자가 직접 적은
주관적 느낌(운동 전후 기분·몸 상태)을 하나의 글로 엮는다.
하루에 여러 운동을 했으면 '오늘의 운동' 한 편으로 합쳐서 작성한다.
"""
from core import writer

ZONE_LABELS = {
    "zone0": "존0(안정)",
    "zone1": "존1(가벼움)", "zone2": "존2(지방연소)", "zone3": "존3(유산소)",
    "zone4": "존4(고강도)", "zone5": "존5(최대)",
}

# 존별 색 (앱 내 막대 그래프용): 안정→최대 순으로 차분한 색→강한 색
ZONE_COLORS = {
    "zone0": "#cbd5e1", "zone1": "#94a3b8", "zone2": "#38bdf8",
    "zone3": "#34d399", "zone4": "#fbbf24", "zone5": "#f87171",
}


def zone_line(w):
    """존별 체류시간 한 줄 요약. 예: '존1 8분 · 존2 7분 · ...'"""
    zones = w.get("zones") or {}
    parts = [f"{ZONE_LABELS.get(k, k)} {v}분"
             for k, v in sorted(zones.items()) if v]
    return " · ".join(parts)

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

    def add(label, value, unit=""):
        if value not in (None, ""):
            lines.append(f"  - {label}: {value}{unit}")

    add("운동 시간", w.get("duration_min"), "분")
    dt = _distance_text(w)
    if dt:
        lines.append(f"  - 거리: {dt}")
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
            lines.append(f"  - 심박존 분포: {z}")
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


def analyze_workout(summary, profile=None, trend="", user_note="", whoop_note=""):
    """코치 관점에서 오늘 운동(들)을 해석한다 (초안).

    trend      : 최근 2주 운동·회복 숫자 요약 (whoop_agent.get_trend_summary).
    user_note  : 운동한 사람이 코치에게 직접 전한 추가 정보/정정
                 (예: 명상 습관, 회복도 급락 원인). 데이터보다 우선한다.
    whoop_note : Whoop 앱 코치가 한 말 (사용자가 붙여넣음). 동료 코치의
                 의견으로 참고 — 반복하지 말고 보완한다.
    """
    goal = (profile or {}).get("goals", "")
    goal_line = f"이 사람의 운동 목표: {goal}" if goal else ""
    trend_block = ""
    if trend:
        trend_block = f"""
[최근 2주 운동·회복 추세]
{trend}
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
    prompt = f"""당신은 이 사람을 꾸준히 지켜봐 온 퍼스널 트레이너이자 운동 코치입니다.
아래는 오늘 한 사람의 Whoop 운동 기록입니다. (여러 운동일 수 있습니다)

{summary}
{trend_block}{note_block}{whoop_block}
{goal_line}

이 데이터를 2~3문단으로 해석해주세요:
1. 오늘 운동의 강도·심박존 분포가 의미하는 것 (쉬운 말로)
2. 최근 추세와 비교해 오늘 운동이 어떤 의미인지 — 훈련량이 늘었는지/줄었는지,
   회복도 흐름을 볼 때 잘한 선택이었는지 (추세 데이터가 있을 때만)
3. 다음 운동을 위한 짧은 조언
여러 운동을 했다면 하루 전체 흐름으로 엮어서 봐주세요.
숫자를 단순 나열하지 말고, 오래 함께해 온 코치의 말투로 자연스럽게 풀어주세요."""
    return writer.generate(prompt, model=writer.QUICK_MODEL, max_tokens=1200)


def write_workout_blog(summary, analysis, before, body, after, profile=None,
                       n_workouts=1):
    """데이터 + 코치 분석 + 나의 주관적 느낌을 하나의 운동 일지로 엮는다."""
    tone = (profile or {}).get("tone", "")
    tone_line = f"원하는 글 톤: {tone}" if tone else ""

    if n_workouts > 1:
        structure = (
            "오늘은 여러 운동을 했습니다. 각 운동을 이모지 소제목(예: '🏃 러닝', "
            "'🏋️ 웨이트 트레이닝')으로 구분해 섹션을 나눠 써주세요. 각 섹션 안에서 "
            "그 운동의 데이터와 그때의 느낌을 녹이고, 마지막에 하루 전체를 아우르는 "
            "짧은 마무리 문단(내일의 나에게 건네는 한 문장 포함)을 넣어주세요.")
    else:
        structure = (
            "소제목 없이 일기체로 자연스럽게 이어서 쓰고, 마지막은 내일의 나에게 "
            "건네는 한 문장으로 마무리해주세요.")

    prompt = f"""당신은 운동 일기를 쓰는 블로거입니다.
아래 재료를 '오늘의 운동' 한 편의 진솔한 일지로 엮어주세요.

[오늘의 운동 데이터]
{summary}

[코치의 분석]
{analysis}

[운동 전 나의 기분/컨디션]
{before or '(기록 없음)'}

[운동 중·후 몸 상태]
{body or '(기록 없음)'}

[운동 후 나의 기분]
{after or '(기록 없음)'}

{tone_line}

600~900자로, 객관적인 데이터와 나의 주관적인 느낌을 자연스럽게 섞어주세요.
{structure}"""
    return writer.generate(prompt, max_tokens=1800)
