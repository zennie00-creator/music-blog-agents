"""리서치 토론 모드 — 사용자 · Grok · Claude 삼자 디스커션.

흐름 (한 라운드):
  1. 사용자가 질문/주장을 던진다
  2. Grok이 라이브 검색 기반으로 답한다 (최신 데이터·뉴스 담당)
  3. Claude가 Grok의 답을 검토한다 (비판적 검토 — 동의/반박, 전제와의 충돌)
  4. 반복. '종료' 입력 시 요약 후 insights.md에 아카이브.

토큰 설계 — 매 라운드 전체 대화를 다시 보내지 않는다:
  - LLM에는 [롤링 요약] + [최근 TAIL_KEEP개 발언 원문]만 보낸다
  - 발언이 COMPACT_TRIGGER개를 넘으면 오래된 부분을 요약으로 흡수 (호출 1회)
  - 대화 상태는 discussions/<주제>.json에 저장 → 다음에 이어서 가능
    `--discuss "주제"` = 같은 주제 재개, `--discuss` (주제 생략) = 최근 토론 재개
"""
import json
import os
import re
from datetime import datetime

from core import config
from core.llm import ask_claude, ask_grok
from modes.investment import sources

INSIGHTS_PATH = os.path.join(config.ROOT_DIR, "insights.md")
STATE_DIR = os.path.join(config.ROOT_DIR, "discussions")

TAIL_KEEP = 6         # 최근 발언 6개(≈2라운드)는 원문 유지
COMPACT_TRIGGER = 12  # 발언이 이만큼 쌓이면 오래된 부분을 요약으로 흡수

GROK_SYSTEM = """당신은 거시경제·테크 시장 분석가로서 투자 리서치 토론에 참여합니다.
최신 뉴스·데이터를 검색해 근거를 대며 답하세요. 사실과 추측을 구분하고,
한국어로 간결하게 (10문장 이내) 답하세요."""

CLAUDE_SYSTEM = """당신은 투자 리서치 토론의 비판적 검토자입니다.
방금 나온 Grok의 분석을 검토하세요: 동의하는 부분과 근거가 약한 부분을 구분하고,
빠진 관점이나 반대 시나리오를 제시하세요. 투자자의 장기 전제가 주어져 있으면
그 전제와 충돌하는지도 짚으세요. 결론을 강요하지 말고 판단 재료를 더하세요.
한국어로 간결하게 (10문장 이내)."""

COMPACT_PROMPT = """다음 투자 토론의 오래된 부분을 요약에 흡수하세요.
숫자·종목명·합의점·이견은 반드시 보존하고, 나머지는 압축하세요. 15문장 이내.

[기존 요약]
{summary}

[요약에 흡수할 발언들]
{old_messages}

갱신된 요약만 출력하세요."""

SUMMARY_PROMPT = """아래 삼자 토론을 검토하고 마무리 요약을 작성하세요.

형식:
## 핵심 인사이트
(합의된 것 / 이견이 남은 것 구분해 불릿 3~6개)

## 프로그램 반영 후보
(이 토론에서 나온 것 중 투자 전제(thesis.md)·워치리스트(portfolio.md)·
 신호 모듈에 반영할 만한 것. 없으면 '없음')

[토론 요약]
{summary}

[최근 발언]
{tail}"""


# ── 상태 저장/복원 ──────────────────────────────────────

def _slug(topic: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "-", topic).strip("-")
    return s[:50] or "topic"


def _state_path(topic: str) -> str:
    return os.path.join(STATE_DIR, f"{_slug(topic)}.json")


def _load_state(topic: str):
    path = _state_path(topic)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"topic": topic, "summary": "", "messages": []}


def _save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    state["updated"] = datetime.now().isoformat(timespec="seconds")
    with open(_state_path(state["topic"]), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def latest_topic():
    """가장 최근에 갱신된 토론 주제. 없으면 None."""
    if not os.path.isdir(STATE_DIR):
        return None
    files = [os.path.join(STATE_DIR, f) for f in os.listdir(STATE_DIR) if f.endswith(".json")]
    if not files:
        return None
    with open(max(files, key=os.path.getmtime), encoding="utf-8") as f:
        return json.load(f).get("topic")


# ── 컨텍스트 구성 (토큰 최소화 핵심) ─────────────────────

def _fmt(messages) -> str:
    return "\n\n".join(f"[{s}] {t}" for s, t in messages)


def _context(state, thesis: str) -> str:
    parts = []
    if thesis.strip():
        parts.append(f"[투자자의 장기 전제]\n{thesis.strip()}")
    if state["summary"]:
        parts.append(f"[지금까지의 토론 요약]\n{state['summary']}")
    if state["messages"]:
        parts.append(f"[최근 발언]\n{_fmt(state['messages'])}")
    return "\n\n".join(parts)


def _maybe_compact(state):
    if len(state["messages"]) < COMPACT_TRIGGER:
        return
    old, tail = state["messages"][:-TAIL_KEEP], state["messages"][-TAIL_KEEP:]
    print("  🗜️ 오래된 발언을 요약으로 압축 중...")
    state["summary"] = ask_claude(
        "투자 토론 기록 요약자입니다.",
        COMPACT_PROMPT.format(summary=state["summary"] or "(없음)", old_messages=_fmt(old)),
        max_tokens=2048,
    )
    state["messages"] = tail


def _archive(state, summary: str):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(INSIGHTS_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n\n---\n\n# {stamp} — {state['topic']}\n\n")
        if state["summary"]:
            f.write(f"## 토론 요약 (누적)\n\n{state['summary']}\n\n")
        f.write("## 최근 발언\n\n")
        for speaker, text in state["messages"]:
            f.write(f"**[{speaker}]** {text}\n\n")
        f.write(f"## 마무리 요약 (Claude)\n\n{summary}\n")
    print("\n💾 insights.md에 아카이브 완료 (토론 상태는 discussions/에 유지 — 이어서 가능)")


# ── 공개 API ────────────────────────────────────────────

def ask_once(question: str, thesis: str = "") -> str:
    """단발 리서치 질문 (--ask). Grok 답변을 insights.md에 기록."""
    answer = ask_grok(GROK_SYSTEM + "\n\n" + sources.prompt_block(), question,
                      live_search=True, x_handles=sources.x_handles())
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(INSIGHTS_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n\n---\n\n# {stamp} — 단발 질문\n\n**[나]** {question}\n\n**[Grok]** {answer}\n")
    return answer


def discuss(topic: str, thesis: str = ""):
    """삼자 토론 루프 (--discuss). 이전 상태가 있으면 이어서 진행."""
    state = _load_state(topic)
    resumed = bool(state["messages"] or state["summary"])

    print(f"\n🗣️ 삼자 토론 {'재개' if resumed else '시작'} — 주제: {topic}")
    if resumed and state["summary"]:
        print(f"\n[지금까지의 요약]\n{state['summary']}\n")
    print("   (매 라운드: 나 → Grok 분석 → Claude 검토. '종료' 입력 시 요약 후 저장)\n")

    try:
        user_input = input("나> ").strip() if resumed else topic
    except (EOFError, KeyboardInterrupt):
        user_input = ""
    while user_input and user_input.lower() not in ("종료", "exit", "quit", "q"):
        state["messages"].append(["나", user_input])

        print("🔍 Grok 분석 중...")
        grok_answer = ask_grok(
            GROK_SYSTEM + "\n\n" + sources.prompt_block(),
            f"{_context(state, thesis)}\n\n마지막 발언에 대해 최신 데이터를 근거로 답하세요.",
            live_search=True,
            x_handles=sources.x_handles(),
        )
        state["messages"].append(["Grok", grok_answer])
        print(f"\n[Grok]\n{grok_answer}\n")

        print("🧐 Claude 검토 중...")
        claude_review = ask_claude(
            CLAUDE_SYSTEM,
            f"{_context(state, thesis)}\n\n위 Grok의 마지막 분석을 검토하세요.",
            max_tokens=2048,
        )
        state["messages"].append(["Claude", claude_review])
        print(f"\n[Claude]\n{claude_review}\n")

        _maybe_compact(state)
        _save_state(state)  # 라운드마다 저장 — 중간에 끊겨도 이어서 가능

        try:
            user_input = input("나> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

    if not state["messages"]:
        print("발언이 없어 종료합니다.")
        return ""

    print("\n📝 토론 요약 중...")
    summary = ask_claude(
        CLAUDE_SYSTEM,
        SUMMARY_PROMPT.format(summary=state["summary"] or "(없음)",
                              tail=_fmt(state["messages"])),
        max_tokens=4096,
    )
    print(f"\n{summary}")
    _save_state(state)
    _archive(state, summary)
    return summary
