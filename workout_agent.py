"""운동 데이터 분석 + 운동 일지 작성 (하루 여러 운동 지원).

Whoop의 객관적 숫자(강도·심박존·회복도)와 사용자가 직접 적은
주관적 느낌(운동 전후 기분·몸 상태)을 하나의 글로 엮는다.
하루에 여러 운동을 했으면 '오늘의 운동' 한 편으로 합쳐서 작성한다.
"""
from core import writer

ZONE_LABELS = {
    "zone1": "존1(가벼움)", "zone2": "존2(지방연소)", "zone3": "존3(유산소)",
    "zone4": "존4(고강도)", "zone5": "존5(최대)",
}


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


def format_summary(workouts, recovery=None):
    """운동(들) + 회복 데이터를 사람이 읽기 좋은 요약 텍스트로."""
    lines = []
    total = len(workouts)
    if total > 1:
        lines.append(f"오늘 총 {total}개의 운동을 했습니다.\n")
    for i, w in enumerate(workouts, 1):
        lines += _one_workout_lines(w, i, total)
        lines.append("")
    if recovery:
        rec = []
        if recovery.get("recovery") is not None:
            rec.append(f"오늘 회복도: {recovery['recovery']}%")
        if recovery.get("resting_hr"):
            rec.append(f"안정시 심박수: {recovery['resting_hr']} bpm")
        if recovery.get("hrv"):
            rec.append(f"HRV: {recovery['hrv']} ms")
        if rec:
            lines.append("[오늘 컨디션] " + " / ".join(rec))
    return "\n".join(lines).strip()


def stat_rows(workouts, recovery=None):
    """네이버 HTML 통계 카드용 (label, value) 목록 — 하루 합산 기준."""
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
    if strains:
        label = "최고 Strain" if len(workouts) > 1 else "Strain"
        rows.append((label, max(strains)))
    if total_km:
        rows.append(("거리", f"{round(total_km, 2)} km"))
    if total_kcal:
        rows.append(("칼로리", f"{total_kcal} kcal"))
    if max_hrs:
        rows.append(("최대 심박", f"{max(max_hrs)} bpm"))
    if recovery and recovery.get("recovery") is not None:
        rows.append(("회복도", f"{recovery['recovery']}%"))
    return rows


def analyze_workout(summary, profile=None):
    """코치 관점에서 오늘 운동(들)을 해석한다 (초안)."""
    goal = (profile or {}).get("goals", "")
    goal_line = f"이 사람의 운동 목표: {goal}" if goal else ""
    prompt = f"""당신은 따뜻하지만 전문적인 퍼스널 트레이너이자 운동 코치입니다.
아래는 오늘 한 사람의 Whoop 운동 기록입니다. (여러 운동일 수 있습니다)

{summary}

{goal_line}

이 데이터를 2~3문단으로 해석해주세요:
1. 오늘 운동의 강도·심박존 분포가 의미하는 것 (쉬운 말로)
2. 회복도/컨디션 관점에서 잘한 점과 주의할 점
3. 다음 운동을 위한 짧은 조언
여러 운동을 했다면 하루 전체 흐름으로 엮어서 봐주세요.
숫자를 단순 나열하지 말고, 격려하는 코치의 말투로 자연스럽게 풀어주세요."""
    return writer.generate(prompt, model=writer.QUICK_MODEL, max_tokens=1200)


def write_workout_blog(summary, analysis, before, body, after, profile=None):
    """데이터 + 코치 분석 + 나의 주관적 느낌을 하나의 운동 일지로 엮는다."""
    tone = (profile or {}).get("tone", "")
    tone_line = f"원하는 글 톤: {tone}" if tone else ""
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
여러 운동을 했다면 하루의 흐름으로 이어서 써주세요.
소제목 없이 일기체로 쓰고, 마지막은 내일의 나에게 건네는 한 문장으로 마무리해주세요."""
    return writer.generate(prompt, max_tokens=1800)
