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
    """초안을 사용자 피드백에 맞게 다듬는다.

    context: 음악/운동 등 도메인 맥락 한 줄 (선택).
    """
    prompt = f"""다음 {content_type} 내용을 사용자 피드백에 맞게 수정해주세요.
{context}

[원본]
{original}

[사용자 피드백]
{feedback}

같은 형식과 분량을 유지하면서 피드백을 반영해주세요."""
    return generate(prompt)
