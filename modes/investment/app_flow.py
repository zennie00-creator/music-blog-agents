"""📈 투자 토론 모드 (Streamlit) — 브리핑 → 토론 → 일지를 한 화면에서.

설계 요지:
- 오늘 브리핑은 Notion에서 읽는다. 발행된 페이지가 단일 진실이고, 앱 재배포와
  무관하며, repo에 저널을 커밋할 필요도 없다.
- 토론 기록을 파일에 두지 않는다. Streamlit Cloud의 파일시스템은 임시라
  재시작하면 사라지므로, 대화는 세션에 담고 결론은 Notion 일지로 남긴다.
- public 앱이므로 비밀번호 게이트를 먼저 통과해야 한다 (투자 기록은 사적 정보).
"""
import os
from datetime import date as _date

import streamlit as st

from core import notion
from core.llm import ask_claude
from modes.investment import discussion, discussion_store
from modes.investment.journal_agent import write_journal
from modes.investment.pipeline import load_thesis, load_trades

REVIEWER = "Claude(검토)"


def _password_ok() -> bool:
    """공개 배포 앱이라 투자 모드는 잠근다. 키가 없으면 잠금 자체를 알린다."""
    if st.session_state.iv_unlocked:
        return True
    secret = ""
    try:
        secret = st.secrets.get("INVEST_PASSWORD", "")
    except Exception:
        pass          # secrets.toml이 없는 로컬 실행
    secret = secret or os.environ.get("INVEST_PASSWORD", "")
    if not secret:
        st.error("INVEST_PASSWORD가 설정되지 않아 잠겨 있습니다. "
                 "Streamlit Secrets(또는 환경변수)에 추가해 주세요.")
        return False
    with st.form("iv_gate"):
        pw = st.text_input("암호", type="password")
        if st.form_submit_button("열기") and pw:
            if pw == secret:
                st.session_state.iv_unlocked = True
                st.rerun()
            else:
                st.error("암호가 맞지 않습니다.")
    return False


def _briefs_only(pages):
    """토론 기록 페이지를 후보에서 뺀다 — 같은 DB·같은 날짜라 검색에 함께 잡힌다."""
    return [p for p in pages
            if not p["title"].strip().startswith(discussion_store.PREFIX)]


def _load_page(page: dict):
    """선택한 Notion 페이지를 세션에 담는다."""
    st.session_state.iv_brief = notion.read_page(page["id"])
    st.session_state.iv_brief_title = page["title"]
    st.session_state.iv_brief_url = page.get("url", "")


def _context(found: str = "") -> str:
    parts = []
    thesis = load_thesis()
    if thesis.strip():
        parts.append(f"[투자자의 장기 전제]\n{thesis.strip()}")
    if found.strip():
        parts.append(f"[질문에 맞춰 방금 검색한 자료]\n{found.strip()}")
    if st.session_state.iv_brief:
        parts.append("[오늘의 모닝 브리핑 — 이 내용을 전제로 토론한다]\n"
                     + st.session_state.iv_brief)
    if st.session_state.iv_messages:
        parts.append("[지금까지의 대화]\n" + "\n\n".join(
            f"[{s}] {t}" for s, t in st.session_state.iv_messages))
    return "\n\n".join(parts)


def _round(question: str):
    """한 라운드: 리서치 발언 → 비판적 검토."""
    st.session_state.iv_messages.append(("나", question))
    # 브리핑 밖 질문에도 답할 수 있게, 질문에 맞는 기사·공시를 새로 찾아 근거에 더한다
    with st.spinner("질문에 맞는 자료 검색 중..."):
        try:
            found = discussion.search_for_question(question)
        except Exception as e:
            found = ""
            st.warning(f"자료 검색 실패 — 브리핑 근거로만 답합니다: {e}")
    # 무엇을 근거로 답했는지 보이게 한다. 질문마다 쌓아 둔다 —
    # 덮어쓰면 앞선 질문의 근거를 다시 볼 수 없다.
    st.session_state.iv_sources.append({"q": question, "md": found})
    if not found:
        st.info("이번 질문에 대해 외부 자료(공시·기사)를 찾지 못했습니다 — "
                "브리핑·전제 범위에서만 답합니다.")
    ctx = _context(found)
    with st.spinner("리서치 분석 중..."):
        try:
            who, ans = discussion._research(
                f"{ctx}\n\n마지막 발언에 대해 근거를 들어 답하세요.")
        except Exception as e:
            who, ans = "리서치", f"(분석 실패: {e})"
    st.session_state.iv_messages.append((who, ans))
    with st.spinner("검토 중..."):
        try:
            review = ask_claude(
                discussion.CLAUDE_SYSTEM,
                f"{_context(found)}\n\n위 {who}의 마지막 분석을 검토하세요.",
                max_tokens=2048)
        except Exception as e:
            review = f"(검토 실패: {e})"
    st.session_state.iv_messages.append((REVIEWER, review))


def _review_last():
    """마지막 리서치 발언에 대한 검토만 다시 실행 (라운드가 중간에 끊겼을 때)."""
    msgs = st.session_state.iv_messages
    who = next((s for s, _ in reversed(msgs) if s not in ("나", REVIEWER)), "리서치")
    found = (st.session_state.iv_sources or [{}])[-1].get("md", "")
    with st.spinner("검토 중..."):
        try:
            review = ask_claude(discussion.CLAUDE_SYSTEM,
                                f"{_context(found)}\n\n위 {who}의 마지막 분석을 검토하세요.",
                                max_tokens=2048)
        except Exception as e:
            review = f"(검토 실패: {e})"
    msgs.append((REVIEWER, review))


def _sync_discussion():
    """새 발언을 Notion 토론 페이지에 덧붙인다 (append 커서로 중복 방지).

    Streamlit Cloud는 세션이 끊기면 대화가 사라지고, Actions는 이 페이지를 통해서만
    오늘의 토론을 볼 수 있다. 실패해도 화면의 대화는 그대로 두고 경고만 띄운다."""
    msgs = st.session_state.iv_messages
    fresh = msgs[st.session_state.iv_synced:]
    if not fresh:
        return
    try:
        discussion_store.append(fresh)
        st.session_state.iv_synced = len(msgs)
    except Exception as e:
        st.warning(f"토론을 Notion에 저장하지 못했습니다 (화면 기록은 유지): {e}")


def _restore_discussion(day: str):
    """세션이 끊겼다 돌아왔을 때 오늘의 토론을 Notion에서 되살린다.

    하루에 한 번만 시도한다 — 매 rerun마다 조회하면 화면이 느려진다."""
    if st.session_state.iv_restored == day or st.session_state.iv_messages:
        return
    st.session_state.iv_restored = day
    try:
        saved = discussion_store.load(day)
    except Exception:
        return          # 저장된 게 없거나 조회 실패 — 새 토론으로 시작
    if saved:
        st.session_state.iv_messages = saved
        st.session_state.iv_synced = len(saved)
        st.info(f"오늘 저장된 토론 {len(saved)}개 발언을 Notion에서 불러왔습니다.")


def _publish_journal(memo: str, publish: bool):
    """토론과 메모로 투자 일지를 만들고 Notion에 발행."""
    day = _date.today().isoformat()
    notes = "\n\n".join(f"[{s}] {t}" for s, t in st.session_state.iv_messages)
    journal = write_journal(
        day,
        market_data=st.session_state.iv_brief or "(브리핑 없음)",
        analysis="(오늘 브리핑을 위 데이터로 대신함)",
        memo=memo,
        thesis=load_thesis(),
        trades=load_trades(),
        discussion_notes=notes,
    )
    url = ""
    if publish:
        url = notion.publish_page(f"📈 투자 일지 — {day}", journal)
    return journal, url


def _notion_key() -> str:
    """투자용 키가 없으면 기존 모드가 쓰는 NOTION_TOKEN을 쓴다 (같은 통합이면 동일)."""
    key = os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_TOKEN", "")
    if key:
        os.environ["NOTION_API_KEY"] = key
        notion.config.NOTION_API_KEY = key
    return key


def _pick_database() -> bool:
    """DB ID가 없으면 접근 가능한 DB를 보여주고 고르게 한다.

    ID를 URL에서 손으로 뽑는 것보다 안전하고, 값을 모르는 상태에서도 바로 쓸 수 있다."""
    chosen = st.session_state.get("iv_db_id") or os.environ.get("NOTION_DATABASE_ID", "")
    if chosen:
        notion.config.NOTION_DATABASE_ID = chosen
        return True
    st.warning("`NOTION_DATABASE_ID`가 없습니다. 아래에서 투자 일지 데이터베이스를 고르세요.")
    try:
        dbs = notion.list_databases()
    except Exception as e:
        st.error(f"데이터베이스 목록 조회 실패: {e}")
        return False
    if not dbs:
        st.error("이 통합이 접근할 수 있는 데이터베이스가 없습니다. "
                 "Notion에서 해당 DB를 열고 ⋯ → 연결 → 통합을 추가해 주세요.")
        return False
    labels = [d["title"] for d in dbs]
    i = st.selectbox("데이터베이스", range(len(dbs)), format_func=lambda x: labels[x])
    if st.button("이 DB 사용", type="primary"):
        st.session_state.iv_db_id = dbs[i]["id"]
        notion.config.NOTION_DATABASE_ID = dbs[i]["id"]
        st.rerun()
    st.caption("고른 뒤에도 매번 선택하지 않으려면 Secrets에 "
               "`NOTION_DATABASE_ID`로 저장해 두세요 (선택하면 값이 표시됩니다).")
    return False


def _config_ok() -> bool:
    """필요한 키가 있는지 먼저 보여준다 — 없으면 조회가 조용히 실패해 원인을 못 찾는다."""
    if not _notion_key():
        st.error("`NOTION_API_KEY`(또는 `NOTION_TOKEN`)가 없습니다 — 브리핑 읽기·일지 발행에 필요합니다.")
        st.caption("Streamlit Cloud → Manage app → Settings → Secrets 에 추가해 주세요.")
        return False
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("`ANTHROPIC_API_KEY`가 없습니다 — 토론·일지 작성에 필요합니다.")
        return False
    if not _pick_database():
        return False
    if st.session_state.get("iv_db_id"):
        st.caption(f"DB: `{st.session_state.iv_db_id}` "
                   "— Secrets의 `NOTION_DATABASE_ID`에 넣으면 다음부터 자동입니다.")
    if not os.environ.get("XAI_API_KEY"):
        st.caption("ℹ️ XAI_API_KEY 없음 — 리서치 역할은 Claude가 대행합니다.")
    return True


def run():
    if not _password_ok():
        return
    if not _config_ok():
        return

    day = st.date_input("날짜", value=_date.today()).isoformat()
    _restore_discussion(day)
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("브리핑 찾기", use_container_width=True):
            with st.spinner("Notion에서 찾는 중..."):
                try:
                    st.session_state.iv_candidates = _briefs_only(
                        notion.list_pages(day, limit=10))
                    # 그 날짜로 못 찾으면 최근 목록을 보여준다 — 제목 형식이
                    # 예상과 다를 수 있으므로 실제로 무엇이 있는지 보여야 한다.
                    st.session_state.iv_fallback = (
                        [] if st.session_state.iv_candidates
                        else _briefs_only(notion.list_pages("", limit=10)))
                except Exception as e:
                    st.error(f"조회 실패: {e}")
    with col2:
        if st.session_state.iv_brief_url:
            st.caption(f"불러옴: [{st.session_state.iv_brief_title}]"
                       f"({st.session_state.iv_brief_url})")

    cands = st.session_state.get("iv_candidates") or []
    if cands:
        # 하루에 여러 번 발행됐을 수 있다 → 고르게 한다 (기본값은 가장 최근 것)
        labels = [f"{c['created']} KST · {c['title']}" for c in cands]
        idx = 0 if len(cands) == 1 else st.selectbox(
            f"{len(cands)}건 발견 — 어느 것을 쓸까요 (발행 시각 KST)",
            range(len(cands)), format_func=lambda i: labels[i])
        if st.button("이 페이지 불러오기", type="primary"):
            with st.spinner("본문 읽는 중..."):
                try:
                    _load_page(cands[idx])
                    st.session_state.iv_candidates = []
                    st.rerun()
                except Exception as e:
                    st.error(f"읽기 실패: {e}")

    fb = st.session_state.get("iv_fallback") or []
    if fb:
        st.warning(f"{day} 제목의 페이지가 없습니다. DB의 최근 페이지는 이렇습니다 — "
                   "제목 형식이 다르거나 다른 DB일 수 있습니다.")
        for c in fb:
            st.caption(f"· {c['created']} KST · {c['title']}")

    if st.session_state.iv_brief:
        with st.expander("오늘의 브리핑", expanded=not st.session_state.iv_messages):
            st.markdown(st.session_state.iv_brief)

    st.divider()
    st.subheader("토론")
    if not st.session_state.iv_brief:
        st.caption("브리핑을 먼저 불러오면 신호·클러스터·뉴스를 공유한 상태로 토론합니다.")

    srcs = st.session_state.get("iv_sources") or []
    if srcs:
        st.caption("참고 자료 (질문별로 누적)")
        for i, s in enumerate(srcs, 1):
            head = s["q"][:34] + ("…" if len(s["q"]) > 34 else "")
            with st.expander(f"{i}. {head}", expanded=(i == len(srcs))):
                st.markdown(s["md"] or "_외부 자료를 찾지 못했습니다 "
                                       "(브리핑·전제 범위에서만 답변)._")

    for speaker, text in st.session_state.iv_messages:
        with st.chat_message("user" if speaker == "나" else "assistant"):
            if speaker != "나":
                st.caption(speaker)
            st.markdown(text)

    # 라운드가 중간에 끊기면 검토가 빠진 채로 남는다 → 그 부분만 다시 돌릴 수 있게
    msgs = st.session_state.iv_messages
    if msgs and msgs[-1][0] not in ("나", REVIEWER):
        st.caption("검토 의견이 아직 없습니다 (연결이 끊겼을 수 있습니다).")
        if st.button("검토 다시 실행"):
            _review_last()
            _sync_discussion()
            st.rerun()

    if q := st.chat_input("질문이나 생각을 입력하세요"):
        _round(q)
        _sync_discussion()
        st.rerun()

    if st.session_state.iv_messages:
        st.divider()
        st.subheader("투자 일지")
        memo = st.text_area("오늘의 메모", value=st.session_state.iv_memo,
                            placeholder="매매·판단·느낌을 자유롭게")
        st.session_state.iv_memo = memo
        publish = st.checkbox("Notion에 발행", value=True)
        if st.button("일지 작성", type="primary"):
            with st.spinner("작성 중..."):
                try:
                    journal, url = _publish_journal(memo, publish)
                    st.success(f"발행 완료: {url}" if url else "작성 완료 (발행 생략)")
                    st.markdown(journal)
                except Exception as e:
                    st.error(f"실패: {e}")
