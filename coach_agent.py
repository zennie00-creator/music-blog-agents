"""운동 코치 전담 에이전트 — 운동생리학에 밝은 하이브리드(근력+지구력) 코치.

일지 '글쓰기'(workout_agent)와 분리해서, '분석·처방·플랜 유지'라는 값진
추론만 강한 모델(Opus)로 담당한다. 살아있는 '훈련 프레임워크'
(profile.coach_framework)를 매번 참고하고, 필요하면 갱신을 제안한다.

프레임워크의 뿌리는 사용자가 이미 다른 코치(예: Whoop 코치)와 쌓아 온
대화다. distill_framework()로 그 대화를 '한 번만' 구조화해 프레임워크로
삼으면, 이후로는 평소 일지 흐름만으로 코치가 이어서 발전시킨다.
"""
from core import writer

# 무거운 추론(분석·처방·프레임워크 정리)은 강한 모델로. 글쓰기와 분리.
COACH_MODEL = writer.WRITER_MODEL

# 코치의 정체성·전문성·안전 규칙 — 모든 분석 프롬프트 앞에 붙는다.
COACH_PERSONA = """당신은 이 사람을 오래 지켜봐 온 전담 운동 코치입니다.
지구력과 근력을 함께 하는 '하이브리드' 선수를 전문으로 코칭하며,
운동생리학을 실제로 이해하고 그 언어로 추론합니다:
- VO₂max와 유산소 능력, '러닝 이코노미/에어로빅 효율'(같은 페이스에 심박이
  낮아지면 그 페이스가 몸에 '더 싸진' 것 = 좋아진 신호)
- 심박존, cardiac drift(같은 강도에서 심박이 서서히 오르는 현상)
- HRV·안정시심박(RHR)·회복도로 읽는 자율신경 피로
- DOMS(지연성 근육통) 타이밍과 concurrent training(근력·유산소 동시 훈련)의
  간섭 — 특히 '다리가 병목'인 사람의 러닝 컨디션에 미치는 영향
- 주기화와 점진적 과부하, 벤치마크 세션으로 몇 주 흐름을 비교하는 법

지킬 규칙:
- 근거로 추론하되 쉬운 말로. 숫자만 나열하지 말고 '그래서 뭘 의미하는지'를 말한다.
- 뻔한 칭찬("대단해요!")을 남발하지 않는다. 잘한 건 구체적 근거로 한 번만 짚는다.
- 주어진 수치만 쓴다. 없는 날짜·수치를 지어내지 않는다. 모르면 모른다고 한다.
- 의학적 진단·처방은 하지 않는다. 통증·부상·이상 징후(가슴 통증 등)는
  전문가(의사/물리치료사)를 권한다.
- 카톡 보내는 코치처럼 편하게. "~하시길 바랍니다" 격식체 대신 "~해보자/해보면 좋겠어".
"""

# Whoop 개발자 API의 한계 — 코치가 없는 데이터를 있는 척하지 않게 알려준다.
_DATA_CAVEAT = """[데이터 한계 — 반드시 감안]
Whoop 개발자 API는 심박 시계열·구간별 스플릿·VO₂Max를 주지 않는다. 그래서
아래 '오늘 데이터'는 세션 요약치(평균/최대 심박·존 체류·강도)뿐이다.
사용자가 직접 적어준 스플릿(예: 속도×시간)이나 VO₂Max가 있으면 그걸 우선 근거로 쓰고,
없는 세부는 추정하지 말고 '다음엔 이 값을 알려달라'고 짧게 요청하라."""


def _framework_block(framework):
    fw = (framework or "").strip()
    if not fw:
        return ""
    return f"""
[현재 훈련 프레임워크 — 이 선수의 '살아있는 플랜'. 이 위에서 코칭할 것]
{fw}

프레임워크 사용 규칙:
- 오늘 세션이 이 플랜의 어느 세션(예: 크루즈 테스트/인터벌/회복)인지 짚어라.
- 오늘이 플랜과 어긋났으면(피곤/일정) 그걸 인정하고 조정안을 준다.
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
                          coach_log="", user_note="", whoop_note=""):
    """분석 프롬프트를 조립한다 (테스트·재사용을 위해 순수 함수로 분리)."""
    return f"""{COACH_PERSONA}

아래는 오늘(또는 지난 어느 날) 이 사람이 한 운동 기록입니다. (여러 운동일 수 있음)

[오늘 운동 데이터]
{summary}

{_DATA_CAVEAT}
{_framework_block(framework)}{_trend_block(trend)}{_log_block(coach_log)}{_note_block(user_note, whoop_note)}
{_goal_block(profile)}

다음 순서로, 오래 함께한 코치가 카톡 보내듯 편하게 풀어주세요
(소제목·번호는 붙이지 말고 문단으로 자연스럽게 이어서):
1) 오늘 세션이 생리학적으로 뭘 의미하는지 — 강도·심박존·효율 관점에서 쉬운 말로.
2) 최근 추세·프레임워크와 견줘 오늘의 위치 — 플랜의 어떤 세션이었고 잘한 선택이었는지
   (추세·프레임워크 데이터가 있을 때만).
3) 다음 세션 처방 — 구체적으로(페이스/시간/존/요일). 다리 소어·회복 상태를 감안.
4) 필요하면 마지막에 한 줄로 프레임워크·베이스라인 갱신 제안
   ("→ 프레임워크 제안: ..." 형식. 없으면 생략).

3~5문단. 상투적 감동·명언투 금지."""


def analyze(summary, profile=None, framework="", trend="", coach_log="",
            user_note="", whoop_note=""):
    """오늘 운동을 전문가 코치 관점으로 해석한다 (강한 모델)."""
    prompt = build_analysis_prompt(summary, profile, framework, trend,
                                    coach_log, user_note, whoop_note)
    return writer.generate(prompt, model=COACH_MODEL, max_tokens=2000)


def build_distill_prompt(existing, source_text):
    return f"""당신은 위와 같은 전문 운동 코치입니다. 아래는 이 선수가 다른 코치
(예: Whoop 코치)와 나눈 대화이거나 본인이 적은 훈련 메모입니다.
여기서 '앞으로 계속 쓸 훈련 프레임워크'를 구조화된 한국어 마크다운으로 뽑아주세요.

[기존 프레임워크]
{(existing or '').strip() or '(아직 없음)'}

[새 자료]
{source_text.strip()}

아래 섹션으로 정리하세요(해당 내용이 없으면 그 섹션은 생략):
## 목표
## 제약 / 주의 (부상·소어 타이밍·컨디션 패턴 등)
## 주간 템플릿 (요일별 — 있으면)
## 벤치마크 & 진행 신호 (무엇을 어떻게 비교하는지)
## 베이스라인 (현재까지의 기준 수치)
## 코치 메모 (그 밖에 계속 기억할 것)

규칙:
- 기존 프레임워크와 새 자료를 합치되, 충돌하면 최신 정보를 우선한다.
- 자료에 실제로 있는 것만 적는다. 수치·계획을 추측으로 지어내지 않는다.
- 간결하게. 각 항목은 한 줄 불릿으로.
- 설명·인사말 없이 프레임워크 마크다운만 출력한다."""


def distill_framework(existing, source_text):
    """다른 코치와의 대화/메모를 구조화된 훈련 프레임워크로 증류(+기존과 병합).

    '캐치업'에 쓴다 — 한 번 돌려 프레임워크를 세워 두면, 이후엔 평소 일지
    흐름(coach_log·coach_memory)만으로 코치가 이어서 발전시킨다.
    """
    if not (source_text or "").strip():
        return (existing or "").strip()
    prompt = COACH_PERSONA + "\n\n" + build_distill_prompt(existing, source_text)
    return writer.generate(prompt, model=COACH_MODEL, max_tokens=1500).strip()
