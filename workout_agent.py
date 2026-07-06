"""운동 데이터 분석 + 운동 일지 작성.

Whoop의 객관적 숫자(강도·심박수·회복도)와 사용자가 직접 적은
주관적 느낌(운동 전후 기분·몸 상태)을 하나의 글로 엮는다.
"""
from core import writer


def format_summary(workout, recovery=None):
    """운동/회복 데이터를 사람이 읽기 좋은 요약 텍스트로."""
    lines = []

    def add(label, value, unit=""):
        if value not in (None, ""):
            lines.append(f"- {label}: {value}{unit}")

    add("종목", workout.get("sport"))
    add("운동 시간", workout.get("duration_min"), "분")
    if workout.get("distance_m"):
        add("거리", round(workout["distance_m"] / 1000, 2), "km")
    add("Strain(운동 강도, 0~21)", workout.get("strain"))
    add("평균 심박수", workout.get("avg_hr"), " bpm")
    add("최대 심박수", workout.get("max_hr"), " bpm")
    add("소모 칼로리", workout.get("kcal"), " kcal")
    if recovery:
        add("오늘 회복도", recovery.get("recovery"), "%")
        add("안정시 심박수", recovery.get("resting_hr"), " bpm")
        add("HRV", recovery.get("hrv"), " ms")
    return "\n".join(lines)


def stat_rows(workout, recovery=None):
    """네이버 HTML 통계 카드에 넣을 (label, value) 목록."""
    rows = []
    if workout.get("strain") is not None:
        rows.append(("Strain", workout["strain"]))
    if workout.get("avg_hr"):
        rows.append(("평균 심박", f'{workout["avg_hr"]} bpm'))
    if workout.get("kcal"):
        rows.append(("칼로리", f'{workout["kcal"]} kcal'))
    if workout.get("distance_m"):
        rows.append(("거리", f'{round(workout["distance_m"]/1000, 2)} km'))
    if recovery and recovery.get("recovery") is not None:
        rows.append(("회복도", f'{recovery["recovery"]}%'))
    return rows


def analyze_workout(summary, profile=None):
    """코치 관점에서 오늘 운동 데이터를 해석한다 (초안)."""
    goal = (profile or {}).get("goals", "")
    goal_line = f"이 사람의 운동 목표: {goal}" if goal else ""
    prompt = f"""당신은 따뜻하지만 전문적인 퍼스널 트레이너이자 운동 코치입니다.
아래는 오늘 한 사람의 Whoop 운동 기록입니다.

{summary}

{goal_line}

이 데이터를 2~3문단으로 해석해주세요:
1. 오늘 운동의 강도와 심박수가 의미하는 것 (쉬운 말로)
2. 회복도/컨디션 관점에서 잘한 점과 주의할 점
3. 다음 운동을 위한 짧은 조언
숫자를 단순 나열하지 말고, 격려하는 코치의 말투로 자연스럽게 풀어주세요."""
    return writer.generate(prompt, model=writer.QUICK_MODEL, max_tokens=1024)


def write_workout_blog(summary, analysis, before, body, after, profile=None):
    """데이터 + 코치 분석 + 나의 주관적 느낌을 하나의 운동 일지로 엮는다."""
    tone = (profile or {}).get("tone", "")
    tone_line = f"원하는 글 톤: {tone}" if tone else ""
    prompt = f"""당신은 운동 일기를 쓰는 블로거입니다.
아래 재료를 하나의 진솔한 운동 일지로 엮어주세요.

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

600~800자로, 객관적인 데이터와 나의 주관적인 느낌을 자연스럽게 섞어주세요.
소제목 없이 일기체로 쓰고, 마지막은 내일의 나에게 건네는 한 문장으로 마무리해주세요."""
    return writer.generate(prompt, max_tokens=1500)
