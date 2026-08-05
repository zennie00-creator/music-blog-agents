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


def _load_brief(day: str):
    """Notion에서 해당 날짜의 모닝 브리핑을 읽어 세션에 담는다."""
    title, body, url = notion.fetch_page_by_title(day)
    st.session_state.iv_brief = body
    st.session_state.iv_brief_title = title
    st.session_state.iv_brief_url = url
    return bool(body)


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


def run():
    if not _password_ok():
        return

    day = st.date_input("날짜", value=_date.today()).isoformat()
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("브리핑 불러오기", use_container_width=True):
            with st.spinner("Notion에서 읽는 중..."):
                try:
                    ok = _load_brief(day)
                    if not ok:
                        st.warning(f"{day} 브리핑을 찾지 못했습니다.")
                except Exception as e:
                    st.error(f"불러오기 실패: {e}")
    with col2:
        if st.session_state.iv_brief_url:
            st.caption(f"[{st.session_state.iv_brief_title}]"
                       f"({st.session_state.iv_brief_url})")

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
