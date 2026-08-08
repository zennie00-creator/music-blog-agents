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

# 출처 표기 규칙 — 리서치·검토 양쪽에 공통 적용
SOURCE_RULE = """

출처 표기:
- 브리핑·전제·검색 자료의 내용을 근거로 쓸 때는 그 문장 끝에 [1], [2] 처럼 각주를 다세요.
- '질문에 맞춰 방금 검색한 자료'가 주어지면 그것을 우선 근거로 삼으세요 —
  브리핑에 없는 질문일수록 이쪽에 답이 있습니다. 기사 제목의 사실만 쓰고,
  본문을 읽은 것처럼 세부를 지어내지 마세요.
- 분기 재무 표(SEC EDGAR)가 있으면 추세를 직접 읽어 답하세요 — 전분기·1년 전 대비
  어떻게 변했는지 수치로 비교하고, 한 분기 값만 보고 단정하지 마세요.
  단, 표의 마진은 GAAP 영업마진이라 보도되는 adjusted·FCF 기준과 다를 수 있음을
  전제하고, 그 차이가 중요한 질문이면 그 점을 밝히세요.
- 답변 맨 끝에 '---' 한 줄을 긋고 각주 목록을 답니다. 형식:
  [1] 브리핑 · 동적 클러스터
  [2] 검색 자료 · "Palantir beats estimates" (CNBC)
  [3] 나의 전제 · 기둥 3(반도체 업황)
  매체명이 있으면 괄호로 함께 적으세요.
- 브리핑·전제에 없는 일반 지식으로 말하는 부분에는 각주를 달지 말고,
  '확인되지 않음' 또는 '일반적으로 알려진 바로는'처럼 성격을 밝히세요.
  실시간 검색이 없으므로 최신 사실을 단정하지 마세요.
- 근거를 댈 게 없으면 각주 목록은 생략합니다."""

GROK_SYSTEM = """당신은 거시경제·테크 시장 분석가로서 투자 리서치 토론에 참여합니다.
주어진 브리핑·전제를 근거로 답하세요. 사실과 추측을 구분하고,
한국어로 간결하게 (10문장 이내) 답하세요.""" + SOURCE_RULE

CLAUDE_SYSTEM = """당신은 투자 리서치 토론의 비판적 검토자입니다.
방금 나온 분석을 검토하세요: 동의하는 부분과 근거가 약한 부분을 구분하고,
빠진 관점이나 반대 시나리오를 제시하세요. 투자자의 장기 전제가 주어져 있으면
그 전제와 충돌하는지도 짚으세요. 상대가 브리핑에 없는 내용을 사실처럼 말했다면
그 점을 지적하세요. 결론을 강요하지 말고 판단 재료를 더하세요.
한국어로 간결하게 (10문장 이내).""" + SOURCE_RULE

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


def _context(state, thesis: str, brief: str = "", found: str = "") -> str:
    parts = []
    if thesis.strip():
        parts.append(f"[투자자의 장기 전제]\n{thesis.strip()}")
    if found.strip():
        parts.append(f"[질문에 맞춰 방금 검색한 자료]\n{found.strip()}")
    if brief.strip():
        # 오늘 브리핑을 토론의 출발점으로 — 신호·클러스터·뉴스를 이미 공유한 상태에서 시작
        parts.append(f"[오늘의 모닝 브리핑 — 이 내용을 전제로 토론한다]\n{brief.strip()}")
    if state["summary"]:
        parts.append(f"[지금까지의 토론 요약]\n{state['summary']}")
    if state["messages"]:
        parts.append(f"[최근 발언]\n{_fmt(state['messages'])}")
    return "\n\n".join(parts)


def load_today_brief(date: str = "") -> str:
    """오늘 발행된 모닝 브리핑 본문 (journals/YYYY-MM-DD-brief.md). 없으면 빈 문자열."""
    from datetime import date as _d
    date = date or _d.today().isoformat()
    path = os.path.join(config.ROOT_DIR, "journals", f"{date}-brief.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


def _sync_notion(state):
    """아직 저장하지 않은 발언을 Notion 토론 페이지에 덧붙인다.

    실패해도 토론은 계속된다 — 로컬 상태(discussions/)가 여전히 남으므로."""
    from modes.investment import discussion_store
    done = state.get("synced", 0)
    fresh = state["messages"][done:]
    if not fresh:
        return
    try:
        discussion_store.append(fresh, topic=state["topic"])
        state["synced"] = len(state["messages"])
    except Exception as e:
        print(f"  ⚠️ Notion 토론 저장 실패 (로컬에는 저장됨): {e}")


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
    # 압축은 Notion 저장 뒤에 일어난다(아래 discuss 루프 순서) — 남은 발언은 이미
    # 전부 저장됐으므로 커서를 길이에 맞춰 되돌린다. 안 그러면 다음 라운드에
    # 저장된 발언을 다시 덧붙인다.
    state["synced"] = len(state["messages"])


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

TERMS_PROMPT = """다음 질문에 답하려면 어떤 뉴스를 찾아야 할까요.

질문: {question}

영문 검색어 2개를 쉼표로만 출력하세요 (설명·따옴표 금지).
회사명·지표명처럼 기사에 실제로 쓰이는 표현으로 만드세요.
예: Palantir Rule of 40 margin, Palantir revenue growth guidance"""


def search_for_question(question: str, per_term: int = 5) -> str:
    """질문에 맞는 기사를 새로 찾아 온다.

    브리핑 안에만 근거를 두면 브리핑 밖 질문에는 '확인되지 않음'밖에 답할 수 없다.
    xAI 라이브 검색은 폐기됐지만 Google News RSS는 살아 있으므로 그걸로 대신한다.
    실패하면 빈 문자열 — 토론은 브리핑 근거만으로 계속된다."""
    from modes.investment.earnings import _news_rss, _render_group
    try:
        raw = ask_claude("검색어를 뽑는 도우미입니다. 요청된 형식만 출력하세요.",
                         TERMS_PROMPT.format(question=question.strip()[:300]),
                         max_tokens=100)
    except Exception as e:
        print(f"  ⚠️ 검색어 추출 실패: {e}")
        return ""
    terms = [t.strip(" \"'\n") for t in raw.replace("\n", ",").split(",")]
    terms = [t for t in terms if 2 < len(t) < 80][:2]
    groups = []
    for t in terms:
        try:
            items = _news_rss(t, when="21d")[:per_term]
        except Exception:
            continue
        if items:
            groups.append(_render_group(t, items))
    news_md = ""
    if groups:
        news_md = ("아래는 이 질문에 맞춰 방금 검색한 기사 헤드라인입니다"
                   " (Google News, 최근 3주). 답변에 쓸 때는 매체명을 출처로 밝히세요:\n\n"
                   + "\n\n".join(groups))

    # 뉴스는 '무슨 일이 있었나'만 답한다. '숫자가 어떻게 변해왔나'는 공시로 본다.
    try:
        from modes.investment import fundamentals
        fin_md = fundamentals.context_for(question)
    except Exception as e:
        print(f"  ⚠️ 재무 시계열 조회 실패: {e}")
        fin_md = ""
    return "\n\n".join(x for x in (fin_md, news_md) if x)


def _research(prompt: str):
    """리서치 발언 담당 — Grok 우선, 불가하면 Claude가 그 역할을 대행.

    Grok이 죽어도(현재 xAI 410) 토론이 멈추지 않게 한다. 대행일 때는 검색이 없으므로
    '단정 금지'를 명시하고, 발언자 이름도 다르게 남겨 누가 말한 것인지 기록에 남긴다.
    → (발언자 이름, 답변)"""
    system = GROK_SYSTEM + "\n\n" + sources.prompt_block()
    if config.USE_GROK:
        try:
            return "Grok", ask_grok(system, prompt, live_search=True,
                                    x_handles=sources.x_handles())
        except Exception as e:
            print(f"  ℹ️ Grok 불가 → Claude가 리서치 역할 대행: {e}")
    note = ("\n\n[안내] 실시간 검색이 없습니다. 주어진 브리핑·전제·대화 내용만 근거로"
            " 답하고, 확인되지 않은 최신 사실은 단정하지 마세요.")
    return "Claude(리서치)", ask_claude(system, prompt + note, max_tokens=2048)


def _notion_insights(date: str) -> str:
    """Notion에 저장된 오늘의 토론 → 일지용 텍스트. 없거나 실패하면 빈 문자열.

    Actions는 매 실행이 새 컨테이너라 discussions/가 존재하지 않는다. 폰(Streamlit)에서
    한 토론이 다음 날 아침 일지에 반영되려면 이 경로가 유일한 통로다."""
    from modes.investment import discussion_store
    parts = []
    for topic, msgs in discussion_store.load_day(date):
        chunk = [f"[토론 주제] {topic or '(오늘의 토론)'}"]
        summaries = [t for s, t in msgs if s == discussion_store.SUMMARY_SPEAKER]
        if summaries:
            chunk.append(f"(마무리 요약) {summaries[-1]}")
        talk = [(s, t) for s, t in msgs if s != discussion_store.SUMMARY_SPEAKER]
        chunk += [f"[{s}] {t}" for s, t in talk[-TAIL_KEEP:]]
        parts.append("\n".join(chunk))
    return "\n\n".join(parts)


def today_insights(date: str = "") -> str:
    """오늘 진행한 토론의 요약·발언 — 투자 일지에 반영할 재료. 없으면 빈 문자열.

    Notion을 먼저 본다(폰·Actions 공용 저장소). 로컬 CLI 토론만 있는 경우를 위해
    discussions/*.json도 이어서 확인한다."""
    from datetime import date as _d
    date = date or _d.today().isoformat()
    try:
        found = _notion_insights(date)
    except Exception as e:
        print(f"  ⚠️ Notion 토론 조회 실패 (로컬 기록만 확인): {e}")
        found = ""
    if found:
        return found
    if not os.path.isdir(STATE_DIR):
        return ""
    parts = []
    for name in sorted(os.listdir(STATE_DIR)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(STATE_DIR, name), encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not str(st.get("updated", "")).startswith(date):
            continue  # 오늘 진행한 토론만
        chunk = [f"[토론 주제] {st.get('topic', name)}"]
        if st.get("summary"):
            chunk.append(f"(누적 요약) {st['summary']}")
        msgs = st.get("messages", [])[-TAIL_KEEP:]
        chunk += [f"[{s}] {t}" for s, t in msgs]
        parts.append("\n".join(chunk))
    return "\n\n".join(parts)


def ask_once(question: str, thesis: str = "") -> str:
    """단발 리서치 질문 (--ask). Grok 답변을 insights.md에 기록."""
    answer = ask_grok(GROK_SYSTEM + "\n\n" + sources.prompt_block(), question,
                      live_search=True, x_handles=sources.x_handles())
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(INSIGHTS_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n\n---\n\n# {stamp} — 단발 질문\n\n**[나]** {question}\n\n**[Grok]** {answer}\n")
    return answer


def discuss(topic: str, thesis: str = "", brief: str = ""):
    """삼자 토론 루프 (--discuss). 이전 상태가 있으면 이어서 진행.

    brief를 주면 오늘 모닝 브리핑을 토론의 출발점으로 삼는다 — 신호·클러스터·뉴스를
    이미 공유한 상태에서 시작하므로 '오늘 시장'을 다시 설명할 필요가 없다."""
    state = _load_state(topic)
    resumed = bool(state["messages"] or state["summary"])

    print(f"\n🗣️ 삼자 토론 {'재개' if resumed else '시작'} — 주제: {topic}")
    if brief:
        print("   📊 오늘 모닝 브리핑을 토론 컨텍스트로 주입 (신호·클러스터·뉴스 공유됨)")
    if resumed and state["summary"]:
        print(f"\n[지금까지의 요약]\n{state['summary']}\n")
    print("   (매 라운드: 나 → Grok 분석 → Claude 검토. '종료' 입력 시 요약 후 저장)\n")

    try:
        user_input = input("나> ").strip() if resumed else topic
    except (EOFError, KeyboardInterrupt):
        user_input = ""
    while user_input and user_input.lower() not in ("종료", "exit", "quit", "q"):
        state["messages"].append(["나", user_input])

        print("🔎 질문에 맞는 자료 검색 중...")
        found = search_for_question(user_input)
        if found:
            print(f"  📄 관련 기사 {found.count('- ')}건 확보")

        print("🔍 리서치 분석 중...")
        researcher, research_answer = _research(
            f"{_context(state, thesis, brief, found)}\n\n"
            "마지막 발언에 대해 최신 데이터를 근거로 답하세요.")
        state["messages"].append([researcher, research_answer])
        print(f"\n[{researcher}]\n{research_answer}\n")

        print("🧐 Claude 검토 중...")
        claude_review = ask_claude(
            CLAUDE_SYSTEM,
            f"{_context(state, thesis, brief, found)}\n\n"
            f"위 {researcher}의 마지막 분석을 검토하세요.",
            max_tokens=2048,
        )
        state["messages"].append(["Claude", claude_review])
        print(f"\n[Claude]\n{claude_review}\n")

        # 라운드마다 저장 — 중간에 끊겨도 이어서 가능.
        # Notion을 먼저 밀어 넣어야 압축으로 잘려 나가는 발언이 유실되지 않는다.
        _sync_notion(state)
        _maybe_compact(state)
        _save_state(state)

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
    _sync_notion(state)
    _save_state(state)
    _archive(state, summary)
    try:
        from modes.investment import discussion_store
        url = discussion_store.save_summary(summary, topic=state["topic"])
        if url:
            print(f"🗣️ Notion 토론 기록: {url}")
    except Exception as e:
        print(f"  ⚠️ Notion 요약 저장 실패: {e}")
    return summary
