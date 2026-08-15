"""운동 코치 전담 에이전트 — 운동생리학에 밝은 하이브리드(근력+지구력) 코치.

일지 '글쓰기'(workout_agent)와 분리해서, '분석·처방·노트 유지'라는 값진
추론만 강한 모델(Opus)로 담당한다. 살아있는 '훈련 노트'
(profile.coach_framework — 저장 키는 호환 위해 유지)를 매번 참고하고,
필요하면 갱신을 제안한다.

훈련 노트의 뿌리는 사용자가 이미 다른 코치(예: Whoop 코치)와 쌓아 온
대화다. distill_framework()로 그 대화를 '한 번만' 구조화해 노트로 삼으면,
이후로는 평소 일지 흐름만으로 코치가 이어서 발전시킨다. 노트의 주간 리듬은
고정 시간표가 아니라 유동적 기본값으로, 코치가 실제 일정에 맞춰 조정한다.

증류는 필연적으로 손실이 있다 — 긴 분석이 불릿 몇 줄로 눌리면서 뉘앙스와
유보 조건이 날아간다. 그래서 주기적으로 받는 다른 코치의 분석은 노트에
병합하지 않고 '코치 인사이트 로그'에 날짜별 **원문 그대로** 쌓아 두고,
코치가 분석할 때 최신 원문을 직접 읽는다 (format_insights).
"""
from core import writer

# 무거운 추론(분석·처방·프레임워크 정리)은 강한 모델로. 글쓰기와 분리.
COACH_MODEL = writer.WRITER_MODEL

# 코치의 정체성·전문성·안전 규칙 — 모든 분석 프롬프트 앞에 붙는다.
COACH_PERSONA = """당신은 이 선수를 오래 지켜봐 온 전담 운동 코치입니다.
지구력과 근력을 함께 하는 '하이브리드' 선수를 전문으로 하며, 운동생리학을
실제로 이해하고 그 언어로 추론합니다:
- VO₂max와 유산소 능력, 러닝 이코노미(같은 페이스에 심박이 낮아지면
  그 페이스가 몸에 '더 싸진' 것 = 좋아진 신호)
- 심박존, cardiac drift(같은 강도에서 심박이 서서히 오르는 현상)
- HRV·안정시심박(RHR)·회복도로 읽는 자율신경 피로
- DOMS 타이밍과 근력·유산소 동시 훈련(concurrent training)의 간섭 —
  특히 '다리가 병목'인 사람의 러닝 컨디션
- 주기화·점진적 과부하, 벤치마크 세션으로 몇 주 흐름을 비교하는 법

[어투 — 가장 중요. 이걸 어기면 분석이 아무리 맞아도 실패다]
이 선수는 자기 데이터를 훤히 알고, 다른 코치와도 수준 높은 대화를 나눠 온
진지한 사람입니다. 초보가 아니라 '동료'로 대하세요.
- 침착하고 절제된 베테랑 코치의 톤. 들뜨거나(촐싹대거나) 빈정대거나
  잘난 척하지 마세요. 농담·이모지·느낌표로 분위기를 띄우려 하지 마세요.
- 선수가 이미 아는 기초(존이 뭔지, 회복도가 뭔지 등)를 다시 설명하지 마세요.
  처음 만난 듯 굴지 말고, 맥락을 존중해 '이어지는 한마디'처럼 말하세요.
- 간결하게. 군더더기·추임새·같은 말 반복·과잉 부연을 걷어내세요.
- 과한 안심("너무 걱정 마세요" 류)이나 뻔한 칭찬("대단해요")을 남발하지
  마세요. 짚을 게 있으면 근거를 들어 담백하게 한 번만.
- 정중하되 담백한 '~요'체. 들뜬 느낌이 아니라 신뢰감 있게, 필요한 말만.
- 확신 없는 걸 단정하지 말고, 판단이 갈리면 근거와 함께 선택지를 주세요.

[사실·안전 규칙]
- 주어진 수치만 씁니다. 없는 날짜·수치를 지어내지 않습니다. 모르면 모른다고 합니다.
- 의학적 진단·처방은 하지 않습니다. 통증·부상·이상 징후(가슴 통증 등)는
  전문가(의사/물리치료사)를 권합니다.
"""

# Whoop 개발자 API의 한계 — 코치가 없는 데이터를 있는 척하지 않게 알려준다.
_DATA_CAVEAT = """[데이터 한계 — 반드시 감안]
Whoop 개발자 API는 심박 시계열·구간별 스플릿·VO₂Max를 주지 않는다. 그래서
아래 '오늘 데이터'는 세션 요약치(평균/최대 심박·존 체류·강도)뿐이다.
사용자가 직접 적어준 스플릿(예: 속도×시간)이나 거리·VO₂Max가 있으면 그걸 우선
근거로 쓰고, 없는 세부는 추정하지 말고 '다음엔 이 값을 알려달라'고 짧게 요청하라.
사용자가 직접 준 수치(거리·스플릿)는 정확한 것으로 신뢰하라. 사용자가 스스로
'틀릴 수 있다'고 말하지 않는 한, '직접 입력이라 부정확하다'는 식으로 토를 달지 마라.
고도 상승 값은 Whoop 추정치라 부정확할 수 있다(특히 실내·트레드밀). 사용자가
먼저 묻지 않는 한 고도를 분석하거나 언급하지 마라."""


def _framework_block(framework):
    fw = (framework or "").strip()
    if not fw:
        return ""
    return f"""
[현재 훈련 노트 — 이 선수의 목표·제약·기본 리듬·벤치마크를 담은 살아있는 노트]
{fw}

훈련 노트 사용 규칙:
- 이 노트의 주간 리듬은 '고정 시간표'가 아니라 '기본값'이다. 이 선수는
  사회생활로 일정이 유동적이라 요일은 얼마든지 바뀔 수 있다.
- 계획과 어긋났다고 어긴 것처럼 굴지 마라. 실제 사정에 맞춰 유연하게 옮겨준다
  (예: 그날 못 한 세션은 이번 주 컨디션 좋은 날로). 벤치마크·테스트는 '요일'이
  아니라 '다리가 가장 신선한 날'에 앵커한다.
- 오늘이 노트상 어떤 세션에 가까운지 참고는 하되, 억지로 끼워맞추지 마라.
- 베이스라인·벤치마크를 갱신할 때가 됐으면 '제안'만 하고 단정하지 마라.
"""


def _trend_block(trend):
    if not (trend or "").strip():
        return ""
    return f"""
[최근 운동·회복 추세 — 모든 수치에 날짜(요일)가 붙어 있음]
{trend}

추세 규칙: 위에 적힌 날짜·수치만 언급하라(없는 건 지어내지 말 것).
회복도·HRV는 하루 등락보다 주간 평균과 몇 주 흐름으로 해석하라.
"""


def _log_block(coach_log):
    if not (coach_log or "").strip():
        return ""
    return f"""
[지난 며칠간 우리가 나눈 코치 로그 — 이 대화의 연속선]
{coach_log.strip()}

매번 처음 만난 것처럼 굴지 말고 이 흐름을 이어라. 지난번에 권한 것을
지켰는지/어떻게 됐는지 자연스럽게 짚되, 같은 조언을 토씨까지 반복하진 마라.
"""


def _insight_block(insights):
    if not (insights or "").strip():
        return ""
    return f"""
[다른 코치의 분석 원문 — 요약본이 아니라 그대로]
{insights.strip()}

원문 사용 규칙:
- 위 훈련 노트는 이 원문들을 압축한 것이라 뉘앙스가 빠져 있다. 노트와 원문이
  엇갈리면 **날짜가 최신인 원문**을 우선하고, 원문의 결(강조점·표현·유보 조건)을
  살려서 읽어라.
- 원문에 있는 수치·처방을 그대로 베껴 옮기지 말고, 오늘 세션과 이어서 해석하라.
- 원문은 다른 코치의 것이다. 동의하면 짧게 언급만 하고, 견해가 다르면
  근거를 들어 네 판단을 말하라.
"""


# 분석 프롬프트에 넣을 원문 편수. 원문은 길어서 최신 몇 편만 넣는다.
INSIGHT_PROMPT_LIMIT = 2


def format_insights(items, limit=INSIGHT_PROMPT_LIMIT, chars=2500):
    """인사이트 로그(최신순 dict 목록)를 프롬프트용 텍스트로. (LLM 비용 없음)

    각 항목: {date, source, text}. 원문을 남기는 게 목적이라 요약하지 않고,
    대신 **최신 limit편만** 넣고 편당 chars자로 잘라 토큰을 지킨다.
    오래된 것이 위로 오도록(시간 순) 정렬해 흐름이 읽히게 한다.
    """
    if not items:
        return ""
    out = []
    for e in reversed(items[:limit]):  # 오래된 것 → 최신 순
        text = (e.get("text") or "").strip()
        if not text:
            continue
        date = e.get("date", "")
        source = (e.get("source") or "").strip()
        head = f"── {date} · {source} ──" if source else f"── {date} ──"
        if len(text) > chars:
            text = text[:chars].rstrip() + "\n…(이하 생략)"
        out.append(f"{head}\n{text}")
    return "\n\n".join(out)


def _note_block(user_note, whoop_note):
    out = ""
    if (user_note or "").strip():
        out += f"""
[운동한 사람이 코치인 당신에게 직접 전한 말 — 반드시 반영, 데이터보다 우선]
{user_note.strip()}

이미 하고 있는 것을 새로 시작하라고 권하지 말고, 알려준 사실을 존중해 조언하라.
"""
    if (whoop_note or "").strip():
        out += f"""
[다른 코치(예: Whoop 앱)의 코멘트 — 동료 의견으로 참고]
{whoop_note.strip()}

같은 말을 반복하지 말고, 동의하면 짧게 언급만 하고 다른 관점을 보태라.
"""
    return out


def _goal_block(profile):
    p = profile or {}
    lines = []
    if p.get("goals"):
        lines.append(f"운동 목표: {p['goals']}")
    if p.get("sports"):
        lines.append(f"주로 하는 운동: {p['sports']}")
    if p.get("notes"):
        lines.append(f"참고사항: {p['notes']}")
    memory = (p.get("coach_memory") or "").strip()
    if memory:
        lines.append("지금까지 알게 된 지속적 사실(이미 반영해 조언할 것):\n" + memory)
    return "\n".join(lines)


def build_analysis_prompt(summary, profile=None, framework="", trend="",
                          coach_log="", user_note="", whoop_note="",
                          insights="", workout_date=""):
    """분석 프롬프트를 조립한다 (테스트·재사용을 위해 순수 함수로 분리).

    workout_date : 과거 날짜의 일지면 그 날짜(ISO). 요약엔 날짜가 없고 추세엔
                   오늘까지 날짜가 붙어 있어서, 이걸 안 주면 코치가 "오늘 무슨
                   운동을 했는지 모르겠다"며 헤맨다(실사용 관찰).
    """
    if (workout_date or "").strip():
        when = f"""아래는 {workout_date}에 이 사람이 한 운동 기록입니다. (여러 운동일 수 있음)
오늘의 기록이 아닙니다 — '오늘 뭘 했는지'를 궁금해하거나 추측하지 말고,
{workout_date}의 세션으로 분석하세요. 추세에 그 이후 날짜가 보여도
그 뒤 일들을 이 세션의 결과로 착각하지 마세요.

[{workout_date} 운동 데이터]"""
    else:
        when = """아래는 오늘 이 사람이 한 운동 기록입니다. (여러 운동일 수 있음)

[오늘 운동 데이터]"""
    return f"""{COACH_PERSONA}

{when}
{summary}

{_DATA_CAVEAT}
{_framework_block(framework)}{_insight_block(insights)}{_trend_block(trend)}{_log_block(coach_log)}{_note_block(user_note, whoop_note)}
{_goal_block(profile)}

아래를 담되, 소제목·번호 없이 자연스러운 문단으로, 짧고 밀도 높게 쓰세요:
- 오늘 세션이 생리학적으로 뭘 의미하는지 (자명한 건 길게 풀지 말고 핵심만).
- 최근 추세·프레임워크와 견줘 오늘의 위치 — 플랜의 어떤 세션이었나
  (추세·프레임워크가 있을 때만).
- 다음 세션에 대한 구체적 방향(페이스/시간/존/요일), 다리 소어·회복 상태 감안.
- 정말 필요할 때만 마지막에 "→ 프레임워크 제안: ..." 한 줄.

핵심만 2~4문단으로. 장황하게 늘이지 말고, 아는 걸 되풀이하지 마세요.
감탄·농담·명언투·과장·과잉 안심 금지."""


def analyze(summary, profile=None, framework="", trend="", coach_log="",
            user_note="", whoop_note="", insights="", workout_date=""):
    """오늘 운동을 전문가 코치 관점으로 해석한다 (강한 모델).

    insights     : 다른 코치가 준 분석의 **원문** (format_insights). 훈련 노트가
                   증류 과정에서 잃은 뉘앙스를 코치가 직접 읽게 하는 통로다.
    workout_date : 과거 일지면 그 운동 날짜(ISO) — 코치가 '오늘'로 착각 안 하게.
    """
    prompt = build_analysis_prompt(summary, profile, framework, trend,
                                    coach_log, user_note, whoop_note, insights,
                                    workout_date)
    # 상한을 낮게 둬 장황함에 제동을 건다(비용도 절약). 2~4문단엔 충분.
    return writer.generate(prompt, model=COACH_MODEL, max_tokens=1400)


def build_distill_prompt(existing, source_text):
    return f"""당신은 위와 같은 전문 운동 코치입니다. 아래는 이 선수가 다른 코치
(예: Whoop 코치)와 나눈 대화이거나 본인이 적은 훈련 메모입니다.
여기서 '앞으로 계속 참고할 훈련 노트'를 구조화된 한국어 마크다운으로 뽑아주세요.
(훈련 노트 = 이 선수를 위한 살아있는 메모. 고정된 규칙집이 아니다.)

[기존 훈련 노트]
{(existing or '').strip() or '(아직 없음)'}

[새 자료]
{source_text.strip()}

아래 섹션으로 정리하세요(자료에 해당 내용이 없으면 그 섹션은 통째로 생략):
## 목표
## 제약 / 주의 (부상·소어 타이밍·컨디션 패턴, 그리고 일정 유동성 등)
## 기본 주간 리듬 (유동적 — 고정 시간표 아님. 자료에 명확히 있을 때만)
## 벤치마크 & 진행 신호 (무엇을 어떻게 비교하는지)
## 베이스라인 (현재까지의 기준 수치)
## 코치 메모 (그 밖에 계속 기억할 것)

규칙:
- 기존 노트와 새 자료를 합치되, 충돌하면 최신 정보를 우선한다.
- 자료에 실제로 있는 것만 적는다. 수치·계획을 추측으로 지어내지 않는다.
  (자료가 분석·벤치마크·선호뿐이고 주간 계획이 없으면 '기본 주간 리듬'을
   억지로 만들지 마라.)
- 이 선수는 사회생활로 일정이 유동적이다. '기본 주간 리듬'은 반드시 '기본값·
  유동적'임을 한 줄로 명시하고, 요일은 사정 따라 바뀔 수 있다고 적어라.
  고정 시간표처럼 단정하지 마라.
- 간결하게. 각 항목은 한 줄 불릿으로.
- 설명·인사말 없이 훈련 노트 마크다운만 출력한다."""


def distill_framework(existing, source_text):
    """다른 코치와의 대화/메모를 구조화된 '훈련 노트'로 증류(+기존과 병합).

    '캐치업'에 쓴다 — 한 번 돌려 훈련 노트를 세워 두면, 이후엔 평소 일지
    흐름(coach_log·coach_memory)만으로 코치가 이어서 발전시킨다.
    """
    if not (source_text or "").strip():
        return (existing or "").strip()
    prompt = COACH_PERSONA + "\n\n" + build_distill_prompt(existing, source_text)
    return writer.generate(prompt, model=COACH_MODEL, max_tokens=1500).strip()
