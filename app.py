import streamlit as st
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import music_flow
import workout_flow
import devlog_flow
import whoop_agent
from core import profile as profile_store

# 배포 버전 표시 (재부팅으로 최신 코드가 반영됐는지 눈으로 확인하는 용도)
APP_VERSION = "2026-07-13 · v6 (개발일지 수정요청+네이버 복사)"

# ── 페이지 설정 ──────────────────────────────────────────
st.set_page_config(page_title="블로그 에이전트", page_icon="🎼", layout="centered")

st.markdown("""
<style>
    .block-container { max-width: 800px; padding-top: 2rem; }
    .song-card {
        background: #f8f9fa; border: 1px solid #dee2e6;
        border-radius: 12px; padding: 16px 20px; margin-bottom: 4px;
    }
    .song-title  { font-size: 15px; font-weight: 600; color: #212529; }
    .song-meta   { font-size: 13px; color: #868e96; margin-top: 3px; }
    .song-reason { font-size: 14px; color: #495057; margin-top: 8px; }
    .section-label {
        font-size: 12px; font-weight: 600; color: #adb5bd;
        text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;
    }
    .content-box {
        background: #fffef7; border: 1px solid #e9e3d0;
        border-radius: 12px; padding: 24px;
        line-height: 1.9; font-size: 15px; white-space: pre-wrap;
        color: #212529;
    }
    .step-pill {
        display: inline-block; background: #007bff; color: white;
        border-radius: 20px; padding: 4px 14px; font-size: 13px; margin-bottom: 16px;
    }
    .img-label { font-size: 11px; color: #adb5bd; text-align: center; margin-top: 4px; }
</style>
""", unsafe_allow_html=True)

# ── 세션 초기화 ───────────────────────────────────────────
DEFAULTS = {
    "mode": None,          # None(모드 선택) | "music" | "workout"
    "step": 0,
    # 음악 모드
    "mood": "",
    "chat_history": [],
    "current_options": None,
    "pending_song": {},
    "album_versions": [],
    "song": {},
    "artist_img": None,
    "album_art": None,
    "info": "",
    "audio": "",
    "blog": "",
    # 운동 모드
    "wk_workouts": [],
    "wk_recovery": {},
    "wk_selected_list": [],
    "wk_summary": "",
    "wk_before": "",
    "wk_body": "",
    "wk_after": "",
    "wk_analysis": "",
    "wk_blog": "",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Whoop OAuth 콜백 처리 ─────────────────────────────────
# Whoop 로그인 후 앱으로 돌아오면 URL에 ?code=... 가 붙는다.
# 이 code를 토큰으로 교환하고 운동 모드로 진입시킨다.
_qp = st.query_params
if "code" in _qp and not st.session_state.get("wk_oauth_done"):
    try:
        whoop_agent.exchange_code(_qp["code"])
        st.session_state.wk_oauth_done = True
        st.session_state.mode = "workout"
        st.session_state.step = "w0"
    except Exception as e:
        st.session_state.wk_oauth_error = str(e)
    st.query_params.clear()
    st.rerun()

# ── 사이드바: 모드별 프로필 설정 ─────────────────────────
with st.sidebar:
    st.caption(f"🟢 버전 {APP_VERSION}")
    if st.session_state.mode:
        if st.button("← 모드 다시 선택", use_container_width=True):
            st.session_state.mode = None
            st.session_state.step = 0
            st.rerun()
        st.divider()

    if st.session_state.mode == "workout":
        st.markdown("### 🏃 나의 운동 프로필")
        st.caption("저장해두면 분석·일지가 내 목표와 톤에 맞게 작성됩니다.")
        p = profile_store.load(profile_store.WORKOUT_PROFILE, profile_store.WORKOUT_DEFAULT)
        goals = st.text_area("운동 목표", value=p.get("goals", ""),
                    placeholder="예: 체지방 감량, 10km 45분 완주, 무릎 부담 없이 지속")
        sports = st.text_input("주로 하는 운동", value=p.get("sports", ""),
                    placeholder="예: 러닝, 웨이트, 요가")
        tone = st.text_input("일지 톤", value=p.get("tone", ""),
                    placeholder="예: 담백한 일기체, 자기격려, 데이터 위주")
        notes = st.text_input("기타", value=p.get("notes", ""),
                    placeholder="예: 오른쪽 무릎 주의")
        if st.button("💾 저장", use_container_width=True):
            profile_store.save(profile_store.WORKOUT_PROFILE,
                {"goals": goals, "sports": sports, "tone": tone, "notes": notes})
            st.success("저장됐습니다!")

    elif st.session_state.mode == "devlog":
        st.markdown("### 📓 개발 일지")
        st.caption("발행 위치: Secrets의 NOTION_DEVLOG_PARENT_ID 페이지. "
                   "없으면 운동일지와 같은 페이지(NOTION_PARENT_ID)로 올라갑니다.")

    else:  # 음악 모드 또는 모드 선택 화면
        st.markdown("### 🎧 나의 오디오 환경")
        st.caption("저장해두면 청취 가이드가 내 환경에 맞게 작성됩니다.")
        p = profile_store.load(profile_store.AUDIO_PROFILE, profile_store.AUDIO_DEFAULT)
        devices = st.text_area("청취 기기", value=p.get("devices", ""),
                    placeholder="예: Sony WH-1000XM5 헤드폰, Sonos Era 300 스피커")
        room = st.text_input("청취 공간", value=p.get("room", ""),
                    placeholder="예: 15평 거실, 작은 서재, 통근 지하철")
        preferences = st.text_area("청취 성향", value=p.get("preferences", ""),
                    placeholder="예: 저음 풍부한 걸 좋아함, 보컬이 선명하게 들리길 원함")
        notes = st.text_input("기타", value=p.get("notes", ""),
                    placeholder="예: 이퀄라이저 Flat 세팅 사용")
        if st.button("💾 저장", use_container_width=True):
            profile_store.save(profile_store.AUDIO_PROFILE,
                {"devices": devices, "room": room,
                 "preferences": preferences, "notes": notes})
            st.success("저장됐습니다!")

# ══════════════════════════════════════════════════════════
# 모드 선택 화면
# ══════════════════════════════════════════════════════════
if st.session_state.mode is None:
    st.title("📔 일지 에이전트")
    st.caption("오늘 어떤 글을 써볼까요? 완성한 글은 네이버·Notion에 올릴 수 있습니다.")
    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### 🎼 음악 감상")
        st.caption("분위기·키워드로 음악을 고르고 감성 에세이를 씁니다.")
        if st.button("음악 글쓰기 →", type="primary", use_container_width=True):
            st.session_state.mode = "music"
            st.session_state.step = 0
            st.rerun()
    with col2:
        st.markdown("### 🏃 오늘 운동")
        st.caption("Whoop 기록에 나의 기분·몸 상태를 더해 운동 일지를 씁니다.")
        if st.button("운동 일지 →", type="primary", use_container_width=True):
            st.session_state.mode = "workout"
            st.session_state.step = "w0"
            st.rerun()
    with col3:
        st.markdown("### 📓 개발 일지")
        st.caption("개발 메모를 다듬어 스크린샷과 함께 Notion에 올립니다.")
        if st.button("개발 일지 →", type="primary", use_container_width=True):
            st.session_state.mode = "devlog"
            st.session_state.step = "d0"
            st.rerun()

# ══════════════════════════════════════════════════════════
# 음악 모드
# ══════════════════════════════════════════════════════════
elif st.session_state.mode == "music":
    st.title("🎼 음악 블로그 에이전트")
    st.caption("분위기나 키워드를 입력하면 단계별로 함께 블로그 글을 완성해 드립니다.")
    st.divider()
    music_flow.run()

# ══════════════════════════════════════════════════════════
# 운동 모드
# ══════════════════════════════════════════════════════════
elif st.session_state.mode == "workout":
    st.title("🏃 운동 블로그 에이전트")
    st.caption("Whoop 데이터와 나의 느낌을 합쳐 운동 일지를 완성해 드립니다.")
    st.divider()
    workout_flow.run()

# ══════════════════════════════════════════════════════════
# 개발 일지 모드
# ══════════════════════════════════════════════════════════
elif st.session_state.mode == "devlog":
    st.title("📓 개발 일지")
    st.caption("개발 메모를 정리해 이미지와 함께 Notion에 발행합니다.")
    st.divider()
    devlog_flow.run()
