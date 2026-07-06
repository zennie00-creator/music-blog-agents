"""운동 모드 Streamlit 흐름.

STEP w0 : 오늘 운동 불러오기 (Whoop) + 운동 선택
STEP w1 : 운동 전후 기분·몸 상태 직접 입력
STEP w2 : 분석 + 운동 일지 초안 → 수정 → 네이버 HTML 저장
"""
import os
import streamlit as st

import whoop_agent
import workout_agent
from core import writer
from core.naver_html import build_naver_html
from core import profile as profile_store


def _profile():
    return profile_store.load(profile_store.WORKOUT_PROFILE, profile_store.WORKOUT_DEFAULT)


def run():
    step = st.session_state.step

    # ── STEP w0: 운동 불러오기 ───────────────────────────────
    if step == "w0":
        st.markdown('<div class="step-pill">🏃 1단계 — 오늘 운동 불러오기</div>',
                    unsafe_allow_html=True)

        if st.session_state.get("wk_oauth_error"):
            st.error(f"Whoop 인증 실패: {st.session_state.wk_oauth_error}")
            st.session_state.wk_oauth_error = ""

        if whoop_agent.is_connected():
            st.success("✅ Whoop 계정 연결됨")
        elif whoop_agent.has_credentials():
            st.warning("Whoop 계정이 아직 연결되지 않았습니다.")
            st.link_button("🔗 Whoop 계정 연결하기", whoop_agent.get_auth_url(),
                           type="primary")
            st.caption("버튼을 누르면 Whoop 로그인 화면으로 이동하고, 승인 후 이 앱으로 자동으로 돌아옵니다.")
            st.divider()
            st.caption("연결 없이 먼저 둘러보려면 아래 데모 데이터로 진행할 수 있습니다.")
        else:
            st.info("ℹ️ Whoop 미연결 상태 — 데모(샘플) 운동 데이터로 흐름을 보여드립니다. "
                    "실제 연동은 WHOOP_CLIENT_ID / SECRET 을 설정한 뒤 가능합니다.")

        st.write("")
        if not st.session_state.wk_workouts:
            if st.button("📥 오늘 운동 불러오기", type="primary"):
                with st.spinner("Whoop에서 데이터를 가져오는 중..."):
                    st.session_state.wk_workouts = whoop_agent.get_recent_workouts(days=1)
                    st.session_state.wk_recovery = whoop_agent.get_latest_recovery()
                st.rerun()
            return

        st.markdown("**불러온 운동을 선택하세요:**")
        for i, w in enumerate(st.session_state.wk_workouts):
            col_card, col_btn = st.columns([5, 1])
            with col_card:
                dist = f' · {round(w["distance_m"]/1000, 2)}km' if w.get("distance_m") else ""
                st.markdown(f"""<div class="song-card">
<div class="song-title">🏃 {w.get('sport','운동')} · {w.get('duration_min','?')}분{dist}</div>
<div class="song-meta">Strain {w.get('strain','-')} &nbsp;|&nbsp; 평균 {w.get('avg_hr','-')}bpm &nbsp;|&nbsp; {w.get('kcal','-')}kcal</div>
</div>""", unsafe_allow_html=True)
            with col_btn:
                st.write("")
                if st.button("선택", key=f"wk_{i}", type="primary"):
                    st.session_state.wk_selected = w
                    st.session_state.wk_summary = workout_agent.format_summary(
                        w, st.session_state.wk_recovery)
                    st.session_state.step = "w1"
                    st.rerun()

        st.write("")
        if st.button("🔄 다시 불러오기"):
            st.session_state.wk_workouts = []
            st.rerun()

    # ── STEP w1: 주관적 기록 입력 ────────────────────────────
    elif step == "w1":
        st.markdown('<div class="step-pill">✍️ 2단계 — 오늘의 기분·몸 상태</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="section-label">불러온 운동 데이터</div>',
                    unsafe_allow_html=True)
        st.markdown(f'<div class="content-box">{st.session_state.wk_summary}</div>',
                    unsafe_allow_html=True)
        st.write("")
        st.caption("Whoop 숫자에 나의 느낌을 더하면 훨씬 생생한 일지가 됩니다. (비워도 됩니다)")

        before = st.text_area("운동 전 기분/컨디션", key="wk_before_in",
                              placeholder="예: 아침부터 몸이 무거웠는데 그래도 나가보자 싶었다")
        body = st.text_area("운동 중·후 몸 상태", key="wk_body_in",
                            placeholder="예: 3km 지나니 리듬이 붙었다. 오른쪽 무릎이 살짝 뻐근")
        after = st.text_area("운동 후 기분", key="wk_after_in",
                             placeholder="예: 땀 흘리고 나니 머리가 맑아지고 개운했다")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("← 운동 다시 선택"):
                st.session_state.step = "w0"
                st.rerun()
        with col2:
            if st.button("분석하고 초안 만들기 →", type="primary"):
                st.session_state.wk_before = before
                st.session_state.wk_body = body
                st.session_state.wk_after = after
                st.session_state.wk_analysis = ""
                st.session_state.wk_blog = ""
                st.session_state.step = "w2"
                st.rerun()

    # ── STEP w2: 분석 + 일지 초안 ────────────────────────────
    elif step == "w2":
        st.markdown('<div class="step-pill">🧠 3단계 — 분석 & 운동 일지</div>',
                    unsafe_allow_html=True)
        prof = _profile()

        if not st.session_state.wk_analysis:
            with st.spinner("코치가 오늘 운동을 분석하는 중..."):
                st.session_state.wk_analysis = workout_agent.analyze_workout(
                    st.session_state.wk_summary, prof)
            st.rerun()

        if not st.session_state.wk_blog:
            with st.spinner("운동 일지를 작성하는 중..."):
                st.session_state.wk_blog = workout_agent.write_workout_blog(
                    st.session_state.wk_summary, st.session_state.wk_analysis,
                    st.session_state.wk_before, st.session_state.wk_body,
                    st.session_state.wk_after, prof)
            st.rerun()

        st.markdown('<div class="section-label">코치의 분석</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="content-box">{st.session_state.wk_analysis}</div>',
                    unsafe_allow_html=True)
        st.write("")
        st.markdown('<div class="section-label">운동 일지 초안</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="content-box">{st.session_state.wk_blog}</div>',
                    unsafe_allow_html=True)
        st.write("")

        feedback = st.text_input("수정 요청 (없으면 비워두고 완성)", key="wk_fb",
            placeholder="예: 더 담백하게, 코치 조언을 짧게, 마무리를 다르게...")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("✏️ 수정 요청", disabled=not feedback.strip()):
                with st.spinner("수정 중..."):
                    ctx = f"운동: {st.session_state.wk_selected.get('sport','')}"
                    st.session_state.wk_blog = writer.revise_with_feedback(
                        "운동 일지", st.session_state.wk_blog, feedback, ctx)
                st.rerun()
        with col2:
            if st.button("✅ 완성 & 저장", type="primary"):
                _save_and_show()
        with col3:
            if st.button("↩️ 처음부터"):
                _reset()

        if st.session_state.get("wk_saved_html"):
            _show_output()


def _save_and_show():
    w = st.session_state.wk_selected
    rec = st.session_state.wk_recovery
    naver_html = build_naver_html(
        title=f"오늘의 운동 — {w.get('sport','운동')}",
        subtitle=f"{w.get('duration_min','?')}분 · Strain {w.get('strain','-')}",
        stat_rows=workout_agent.stat_rows(w, rec),
        body_text=st.session_state.wk_blog,
    )
    base = os.path.dirname(__file__)
    txt_name = "workout_log.txt"
    with open(os.path.join(base, txt_name), "w", encoding="utf-8") as f:
        f.write(f"[운동: {w.get('sport','')}]\n{st.session_state.wk_summary}\n\n"
                f"{st.session_state.wk_blog}")
    st.session_state.wk_saved_html = naver_html
    st.success("💾 저장 완료!")


def _show_output():
    naver_html = st.session_state.wk_saved_html
    tab1, tab2 = st.tabs(["📄 텍스트 다운로드", "🟢 네이버 블로그 HTML"])
    with tab1:
        st.download_button("📥 텍스트 다운로드", data=st.session_state.wk_blog,
            file_name="workout_log.txt", mime="text/plain")
    with tab2:
        st.caption("아래 HTML을 복사해서 네이버 블로그 → 글쓰기 → HTML 편집기에 붙여넣으세요.")
        st.code(naver_html, language="html")
        st.download_button("📥 HTML 다운로드", data=naver_html,
            file_name="workout_log_naver.html", mime="text/html")


def _reset():
    for k in ("wk_workouts", "wk_recovery", "wk_selected", "wk_summary",
              "wk_before", "wk_body", "wk_after", "wk_analysis", "wk_blog",
              "wk_saved_html"):
        st.session_state.pop(k, None)
    st.session_state.mode = None
    st.session_state.step = 0
    st.rerun()
