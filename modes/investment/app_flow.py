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
from modes.investment import discussion
from modes.investment.journal_agent import write_journal
from modes.investment.pipeline import load_thesis, load_trades


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


def _load_page(page: dict):
    """선택한 Notion 페이지를 세션에 담는다."""
    st.session_state.iv_brief = notion.read_page(page["id"])
    st.session_state.iv_brief_title = page["title"]
    st.session_state.iv_brief_url = page.get("url", "")


def _context() -> str:
    parts = []
    thesis = load_thesis()
    if thesis.strip():
        parts.append(f"[투자자의 장기 전제]\n{thesis.strip()}")
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
    ctx = _context()
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
                f"{_context()}\n\n위 {who}의 마지막 분석을 검토하세요.",
                max_tokens=2048)
        except Exception as e:
            review = f"(검토 실패: {e})"
    st.session_state.iv_messages.append(("Claude(검토)", review))


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


def _config_ok() -> bool:
    """필요한 키가 있는지 먼저 보여준다 — 없으면 조회가 조용히 실패해 원인을 못 찾는다."""
    need = {"NOTION_API_KEY": "브리핑 읽기·일지 발행",
            "NOTION_DATABASE_ID": "투자 일지 DB",
            "ANTHROPIC_API_KEY": "토론·일지 작성"}
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        st.error("설정이 빠져 있어 진행할 수 없습니다: "
                 + ", ".join(f"`{k}`({need[k]})" for k in missing))
        st.caption("Streamlit Cloud → Manage app → Settings → Secrets 에 추가한 뒤 "
                   "앱이 재시작되면 사라집니다.")
        return False
    if not os.environ.get("XAI_API_KEY"):
        st.caption("ℹ️ XAI_API_KEY 없음 — 리서치 역할은 Claude가 대행합니다.")
    return True


def run():
    if not _password_ok():
        return
    if not _config_ok():
        return

    day = st.date_input("날짜", value=_date.today()).isoformat()
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("브리핑 찾기", use_container_width=True):
            with st.spinner("Notion에서 찾는 중..."):
                try:
                    st.session_state.iv_candidates = notion.list_pages(day, limit=10)
                    # 그 날짜로 못 찾으면 최근 목록을 보여준다 — 제목 형식이
                    # 예상과 다를 수 있으므로 실제로 무엇이 있는지 보여야 한다.
                    st.session_state.iv_fallback = (
                        [] if st.session_state.iv_candidates
                        else notion.list_pages("", limit=10))
                except Exception as e:
                    st.error(f"조회 실패: {e}")
    with col2:
        if st.session_state.iv_brief_url:
            st.caption(f"불러옴: [{st.session_state.iv_brief_title}]"
                       f"({st.session_state.iv_brief_url})")

    cands = st.session_state.get("iv_candidates") or []
    if cands:
        # 하루에 여러 번 발행됐을 수 있다 → 고르게 한다 (기본값은 가장 최근 것)
        labels = [f"{c['created']} · {c['title']}" for c in cands]
        idx = 0 if len(cands) == 1 else st.selectbox(
            f"{len(cands)}건 발견 — 어느 것을 쓸까요",
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
            st.caption(f"· {c['created']} · {c['title']}")

    if st.session_state.iv_brief:
        with st.expander("오늘의 브리핑", expanded=not st.session_state.iv_messages):
            st.markdown(st.session_state.iv_brief)

    st.divider()
    st.subheader("토론")
    if not st.session_state.iv_brief:
        st.caption("브리핑을 먼저 불러오면 신호·클러스터·뉴스를 공유한 상태로 토론합니다.")

    for speaker, text in st.session_state.iv_messages:
        with st.chat_message("user" if speaker == "나" else "assistant"):
            if speaker != "나":
                st.caption(speaker)
            st.markdown(text)

    if q := st.chat_input("질문이나 생각을 입력하세요"):
        _round(q)
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
