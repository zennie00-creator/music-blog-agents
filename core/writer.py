"""Claude 글쓰기 공통 헬퍼.

음악·운동 파이프라인이 모두 이 모듈을 통해 글을 생성/수정한다.
모델을 바꾸고 싶으면 아래 두 상수만 수정하면 앱 전체에 반영된다.
"""
import os
import anthropic

WRITER_MODEL = "claude-opus-4-6"   # 감성 에세이·블로그 본문 작성용
QUICK_MODEL  = "claude-haiku-4-5"  # 정보 요약·분석 등 가벼운 작업용


def _client():
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def generate(prompt, model=WRITER_MODEL, max_tokens=1500):
    """단일 프롬프트로 텍스트를 생성한다."""
    msg = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def revise_with_feedback(content_type, original, feedback, context=""):
    """초안을 사용자 피드백에 맞게 다듬어 '수정된 전체 본문만' 반환한다.

    context: 음악/운동 등 도메인 맥락 한 줄 (선택).
    """
    prompt = f"""아래는 이미 완성된 {content_type} 원문입니다.
사용자의 '수정 요청'을 반영해서 원문을 다시 써주세요.
{context}

[원문]
{original}

[수정 요청]
{feedback}

반드시 지킬 규칙:
- 수정된 {content_type}의 '전체 본문'만 출력하세요.
- "확인했습니다", "수정했습니다", "~가 맞으시군요" 같은 대화·인사·설명을 절대 넣지 마세요.
- 요청된 부분만 반영하고, 나머지 내용·분량·형식·문체는 그대로 유지하세요.
- 이미 요청대로 되어 있으면 원문을 거의 그대로 다시 출력하세요.
- 원문을 감싸는 따옴표나 머리말 없이, 본문 텍스트만 그대로 출력하세요."""
    return generate(prompt)
