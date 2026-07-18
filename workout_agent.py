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
    "러닝", "달리", "조깅", "걷", "워킹", "하이킹", "등산", "사이클", "자전거",
    "스피닝", "수영", "로잉", "조정", "줄넘기", "인터벌", "트레드밀", "에어로빅",
    "일립티컬", "계단", "축구", "농구", "테니스", "배드민턴", "스쿼시",
    "run", "jog", "walk", "hik", "cycl", "spin", "swim", "row", "hiit",
    "cardio", "stair", "elliptical", "soccer", "basket", "tennis",
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
    notes = (profile or {}).get("notes", "")
    if notes:
        goal_line += f"\n이 사람에 대한 참고사항: {notes}"
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
- 감탄·과장("정말", "너무나", 느낌표)을 남발하지 말고 담백하게. 비유는 글 전체에 많아야 한 번."""


def write_workout_blog(summary, analysis, before, body, after, profile=None,
                       n_workouts=1):
    """데이터 + 코치 분석 + 나의 주관적 느낌을 하나의 운동 일지로 엮는다."""
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
            "느낌을 중심으로 데이터를 한두 개만 녹이세요. 마지막에 하루를 돌아보는 "
            "짧은 문단 하나로 끝내세요.")
    else:
        structure = (
            "소제목 없이 일기체로 자연스럽게 이어서 쓰세요.")

    prompt = f"""당신은 오늘 이 운동을 직접 한 사람입니다. 블로거가 아니라,
운동을 마치고 책상에 앉아 오늘을 남겨두려고 일기를 쓰는 사람입니다.
아래 재료로 '오늘의 운동' 일지 한 편을 쓰세요.

[오늘의 운동 데이터]
{summary}

[코치의 분석 — 내가 코치에게 들은 말. 인상 깊었던 한두 가지만 내 말로 언급]
{analysis}

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
    return writer.generate(prompt, max_tokens=1800)


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


def naturalize(text):
    """이미 쓴 일지에서 'AI가 쓴 티'가 나는 문체만 걷어낸다. 내용·구조는 유지."""
    prompt = f"""아래 운동 일지에서 기계가 쓴 티가 나는 문체만 걷어내고,
사람이 직접 쓴 일기처럼 자연스럽게 다듬어주세요.
사실·내용·구조·분량은 그대로 두고 문장만 손보세요.

{STYLE_RULES}

[일지 원문]
{text}

다듬은 전체 본문만 출력하세요. 설명·인사·머리말 금지."""
    return writer.generate(prompt, max_tokens=max(2000, len(text) + 500))
