"""리서치 토론 모드 — 사용자 · Grok · Claude 삼자 디스커션.

흐름 (한 라운드):
  1. 사용자가 질문/주장을 던진다
  2. Grok이 라이브 검색 기반으로 답한다 (최신 데이터·뉴스 담당)
  3. Claude가 Grok의 답을 검토한다 — 동의/반박, 빠진 관점, 투자 전제와의
     충돌 여부 (비판적 검토 담당)
  4. 반복. '종료' 입력 시 Claude가 핵심 인사이트와 프로그램 반영 후보를
     요약하고, 전체 대화가 insights.md에 아카이브된다.

여기서 얻은 인사이트를 프로그램(전제/신호/워치리스트)에 반영하는 것은
Claude Code 세션에서 이어서 한다 (DEVLOG.md 참고).
"""
import os
from datetime import datetime

from core import config
from core.llm import ask_claude, ask_grok

INSIGHTS_PATH = os.path.join(config.ROOT_DIR, "insights.md")

GROK_SYSTEM = """당신은 거시경제·테크 시장 분석가로서 투자 리서치 토론에 참여합니다.
최신 뉴스·데이터를 검색해 근거를 대며 답하세요. 사실과 추측을 구분하고,
한국어로 간결하게 (10문장 이내) 답하세요."""

CLAUDE_SYSTEM = """당신은 투자 리서치 토론의 비판적 검토자입니다.
방금 나온 Grok의 분석을 검토하세요: 동의하는 부분과 근거가 약한 부분을 구분하고,
빠진 관점이나 반대 시나리오를 제시하세요. 투자자의 장기 전제가 주어져 있으면
그 전제와 충돌하는지도 짚으세요. 결론을 강요하지 말고 판단 재료를 더하세요.
한국어로 간결하게 (10문장 이내)."""

SUMMARY_PROMPT = """아래 삼자 토론 전체를 검토하고 마무리 요약을 작성하세요.

형식:
## 핵심 인사이트
(합의된 것 / 이견이 남은 것 구분해 불릿 3~6개)

## 프로그램 반영 후보
(이 토론에서 나온 것 중 투자 전제(thesis.md)·워치리스트(portfolio.md)·
 신호 모듈에 반영할 만한 것. 없으면 '없음')

토론 내용:
{transcript}"""


def _transcript(history) -> str:
    return "\n\n".join(f"[{speaker}] {text}" for speaker, text in history)


def _archive(topic: str, history, summary: str):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(INSIGHTS_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n\n---\n\n# {stamp} — {topic}\n\n")
        for speaker, text in history:
            f.write(f"**[{speaker}]** {text}\n\n")
        f.write(f"## 마무리 요약 (Claude)\n\n{summary}\n")
    print(f"\n💾 insights.md에 아카이브 완료")


def ask_once(question: str, thesis: str = "") -> str:
    """단발 리서치 질문 (--ask). Grok 답변을 insights.md에 기록."""
    answer = ask_grok(GROK_SYSTEM, question, live_search=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(INSIGHTS_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n\n---\n\n# {stamp} — 단발 질문\n\n**[나]** {question}\n\n**[Grok]** {answer}\n")
    return answer


def discuss(topic: str, thesis: str = ""):
    """삼자 토론 루프 (--discuss). '종료'/'exit' 입력 시 요약 후 아카이브."""
    history = []
    thesis_note = f"\n\n[투자자의 장기 전제]\n{thesis.strip()}" if thesis.strip() else ""

    print(f"\n🗣️ 삼자 토론 시작 — 주제: {topic}")
    print("   (매 라운드: 나 → Grok 분석 → Claude 검토. '종료' 입력 시 요약 후 저장)\n")

    user_input = topic
    while True:
        history.append(("나", user_input))
        transcript = _transcript(history)

        print("🔍 Grok 분석 중...")
        grok_answer = ask_grok(
            GROK_SYSTEM,
            f"지금까지의 토론:\n{transcript}{thesis_note}\n\n"
            f"마지막 발언에 대해 최신 데이터를 근거로 답하세요.",
            live_search=True,
        )
        history.append(("Grok", grok_answer))
        print(f"\n[Grok]\n{grok_answer}\n")

        print("🧐 Claude 검토 중...")
        claude_review = ask_claude(
            CLAUDE_SYSTEM,
            f"지금까지의 토론:\n{_transcript(history)}{thesis_note}\n\n"
            f"위 Grok의 마지막 분석을 검토하세요.",
            max_tokens=2048,
        )
        history.append(("Claude", claude_review))
        print(f"\n[Claude]\n{claude_review}\n")

        try:
            user_input = input("나> ").strip()
        except (EOFError, KeyboardInterrupt):
            user_input = "종료"
        if not user_input or user_input.lower() in ("종료", "exit", "quit", "q"):
            break

    print("\n📝 토론 요약 중...")
    summary = ask_claude(
        CLAUDE_SYSTEM,
        SUMMARY_PROMPT.format(transcript=_transcript(history)),
        max_tokens=4096,
    )
    print(f"\n{summary}")
    _archive(topic, history, summary)
    return summary
