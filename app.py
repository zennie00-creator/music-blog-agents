import streamlit as st
import os, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(__file__))

import music_flow
import workout_flow
import devlog_flow
import whoop_agent
import notion_agent
from core import profile as profile_store
from core import draft

# 배포 버전 표시 (재부팅으로 최신 코드가 반영됐는지 눈으로 확인하는 용도)
APP_VERSION = "2026-07-22 · v17 (최근 5일 선택 · 코치 기억 · 시계열 코치 로그)"

# ── 페이지 설정 ──────────────────────────────────────────
st.set_page_config(page_title="일지 에이전트", page_icon="📔", layout="centered")

# 다이어리 톤 디자인 (design_handoff_diary_agent_redesign 기준)
# 색·타이포·radius 값은 핸드오프의 Design Tokens 그대로.
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;500;600&family=Noto+Sans+KR:wght@300;400;500;600&display=swap');

    html, body, .stApp { font-family: 'Noto Sans KR', system-ui, sans-serif; color: #33392c; }
    .block-container { max-width: 640px; padding-top: 3.4rem; }
    h1, h2, h3 {
        font-family: 'Noto Serif KR', serif !important;
        font-weight: 500 !important; color: #33392c !important;
    }
    hr { border-color: #d8ded0; }

    /* 카드 */
    .song-card {
        background: #fbfcf8; border: 1px solid #dfe6d2;
        border-radius: 16px; padding: 18px 20px; margin-bottom: 4px;
    }
    .song-card:hover { border-color: #b7c7a3; }
    .song-title  {
        font-family: 'Noto Serif KR', serif;
        font-size: 16px; font-weight: 600; color: #33392c;
    }
    .song-meta   { font-size: 12.5px; color: #8b9a7c; margin-top: 4px; }
    .song-reason { font-size: 13.5px; color: #5c6650; margin-top: 10px; line-height: 1.6; }

    .section-label {
        font-size: 12px; font-weight: 600; color: #8b9a7c;
        text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;
    }
    .content-box {
        background: #fbfcf8; border: 1px solid #dfe6d2;
        border-radius: 16px; padding: 22px;
        line-height: 1.9; font-size: 15px; white-space: pre-wrap;
        color: #3a4033;
    }
    .step-pill {
        display: inline-block; background: transparent; color: #8b9a7c;
        padding: 0; font-size: 11.5px; font-weight: 600;
        letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 16px;
    }
    .img-label { font-size: 11px; color: #8b9a7c; text-align: center; margin-top: 4px; }

    /* 대문 */
    .date-label {
        font-size: 11.5px; letter-spacing: 0.1em; color: #8b9a7c;
        text-transform: uppercase;
    }
    .home-title {
        font-family: 'Noto Serif KR', serif;
        font-size: clamp(26px, 4vw, 34px); font-weight: 500;
        margin-top: 14px; line-height: 1.45; color: #33392c;
    }
    .mode-card {
        background: #fbfcf8; border: 1px solid #dfe6d2;
        border-radius: 16px; padding: 20px; min-height: 112px; margin-bottom: 10px;
    }
    .mode-card:hover { border-color: #b7c7a3; }
    .mode-title {
        font-family: 'Noto Serif KR', serif;
        font-size: 18px; font-weight: 600; color: #33392c;
    }
    .mode-desc { font-size: 13px; color: #7c8a6c; margin-top: 6px; line-height: 1.5; }
    .hairline { border: none; border-top: 1px solid #d8ded0; margin: 6px 0; }
    .resume-note { font-size: 13px; color: #697559; padding: 10px 2px; }

    /* Streamlit 위젯 다듬기 */
    .stButton > button, .stDownloadButton > button {
        border-radius: 12px; font-weight: 600; font-size: 13.5px;
    }
    .stButton > button[kind="secondary"], .stDownloadButton > button {
        background: transparent; border: 1px solid #c7d2b5; color: #5f7d51;
    }
    .stButton > button[kind="secondary"]:hover, .stDownloadButton > button:hover {
        border-color: #5f7d51; color: #4a6640; background: #fbfcf8;
    }
    .stButton > button[kind="primary"] { background: #5f7d51; border: none; }
    .stButton > button[kind="primary"]:hover { background: #4a6640; }

    /* info/success 알림을 배지 톤(#e2e7d9)으로 — 경고·오류는 기본색 유지 */
    [data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]),
    [data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {
        background: #e2e7d9 !important; color: #4b5540; border-radius: 12px;
    }
    [data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) p,
    [data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) p {
        color: #4b5540 !important;
    }

    .stTextInput input, .stTextArea textarea, .stNumberInput input {
        background: #fbfcf8 !important;
    }
    [data-baseweb="input"], [data-baseweb="textarea"] {
        background: #fbfcf8 !important; border-radius: 12px !important;
        border-color: #d8ded0 !important;
    }
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
    "wk_cycle": {},
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
def _save_profile(filename, data):
    """프로필 저장 + Notion 백업 결과 안내."""
    backed_up = profile_store.save(filename, data)
    if backed_up:
        st.success("저장됐습니다! (Notion에 백업됨)")
    elif notion_agent.has_settings_credentials():
        st.warning("저장은 됐지만 Notion 백업에 실패했습니다. "
                   "앱이 재시작되면 사라질 수 있어요.")
    else:
        st.success("저장됐습니다!")
        st.caption("ℹ️ Notion(NOTION_TOKEN)을 연결하면 앱이 재시작돼도 "
                   "프로필이 유지됩니다.")


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
        style_mem = st.text_area("🧠 기억된 문체 취향", value=p.get("style_memory", ""),
                    height=120,
                    placeholder="일지를 완성할 때 수정 요청에서 자동으로 추려 쌓입니다. "
                                "직접 고치거나 지워도 됩니다.")
        coach_mem = st.text_area("🧠 코치가 기억하는 사실", value=p.get("coach_memory", ""),
                    height=120,
                    placeholder="코치에게 답장한 내용에서 '지속적 사실·습관·주의사항'을 "
                                "자동으로 추려 쌓습니다. (예: 명상 매일, 오른쪽 무릎 주의) "
                                "직접 고치거나 지워도 됩니다.")
        notes = st.text_input("기타", value=p.get("notes", ""),
                    placeholder="예: 오른쪽 무릎 주의")
        if st.button("💾 저장", use_container_width=True):
            _save_profile(profile_store.WORKOUT_PROFILE,
                {"goals": goals, "sports": sports, "tone": tone,
                 "style_memory": style_mem, "coach_memory": coach_mem, "notes": notes})

    elif st.session_state.mode == "devlog":
        st.markdown("### 📓 개발 일지")
        st.caption("발행 위치: Secrets의 NOTION_DEVLOG_PARENT_ID 페이지. "
                   "없으면 운동일지와 같은 페이지(NOTION_PARENT_ID)로 올라갑니다.")

    elif st.session_state.mode == "music":
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
            _save_profile(profile_store.AUDIO_PROFILE,
                {"devices": devices, "room": room,
                 "preferences": preferences, "notes": notes})

# ══════════════════════════════════════════════════════════
# 모드 선택 화면
# ══════════════════════════════════════════════════════════
def _resume_draft(mode_name, d):
    """저장된 초안을 세션에 복원하고 해당 모드로 진입한다."""
    for k, v in d.items():
        if k.startswith(("wk_", "dv_")) and v is not None:
            st.session_state[k] = v
    st.session_state.mode = mode_name
    default_step = "w0" if mode_name == "workout" else "d0"
    st.session_state.step = d.get("step", default_step)
    st.rerun()


if st.session_state.mode is None:
    now = datetime.now(timezone(timedelta(hours=9)))  # KST
    weekday = "월화수목금토일"[now.weekday()]
    st.markdown(f'<div class="date-label">{now.year}년 {now.month}월 {now.day}일 · '
                f'{weekday}요일</div>', unsafe_allow_html=True)
    st.markdown('<div class="home-title">오늘 하루를<br>어떤 결로<br>남겨볼까요</div>',
                unsafe_allow_html=True)
    st.write("")

    # 끊긴 세션에서 저장된 초안이 있으면 이어서 쓰기 배너 (상하 헤어라인)
    for m, label in (("workout", "운동 일지"), ("devlog", "개발 일지")):
        d = draft.load(m)
        if d:
            st.markdown('<hr class="hairline"/>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([4, 1.4, 0.7])
            with c1:
                st.markdown(f'<div class="resume-note">이어서 쓰던 글이 있어요 · {label} · '
                            f'{draft.age_minutes(d)}분 전</div>', unsafe_allow_html=True)
            with c2:
                if st.button("이어서 쓰기", key=f"resume_{m}", type="primary",
                             use_container_width=True):
                    _resume_draft(m, d)
            with c3:
                if st.button("🗑", key=f"deldraft_{m}", help="초안 삭제",
                             use_container_width=True):
                    draft.clear(m)
                    st.rerun()
            st.markdown('<hr class="hairline"/>', unsafe_allow_html=True)

    st.write("")
    _MODES = (
        ("music",   "음악 감상", "분위기를 고르면, 곡과 함께 짧은 에세이를 씁니다", 0),
        ("workout", "오늘 운동", "기록과 몸 상태를 더해 운동 일지를 남깁니다", "w0"),
        ("devlog",  "개발 일지", "오늘 만든 것을 담백하게 정리한 기록으로 남깁니다", "d0"),
    )
    for col, (mode_key, title, desc, first_step) in zip(st.columns(3), _MODES):
        with col:
            st.markdown(f'<div class="mode-card"><div class="mode-title">{title}</div>'
                        f'<div class="mode-desc">{desc}</div></div>',
                        unsafe_allow_html=True)
            if st.button("쓰기 →", key=f"go_{mode_key}", use_container_width=True):
                st.session_state.mode = mode_key
                st.session_state.step = first_step
                st.rerun()

# ══════════════════════════════════════════════════════════
# 음악 모드
# ══════════════════════════════════════════════════════════
elif st.session_state.mode == "music":
    st.title("음악 감상")
    st.caption("분위기나 키워드를 입력하면 단계별로 함께 글을 완성해 드립니다.")
    st.divider()
    music_flow.run()

# ══════════════════════════════════════════════════════════
# 운동 모드
# ══════════════════════════════════════════════════════════
elif st.session_state.mode == "workout":
    st.title("오늘 운동")
    st.caption("Whoop 데이터와 나의 느낌을 합쳐 운동 일지를 완성해 드립니다.")
    st.divider()
    workout_flow.run()

# ══════════════════════════════════════════════════════════
# 개발 일지 모드
# ══════════════════════════════════════════════════════════
elif st.session_state.mode == "devlog":
    st.title("개발 일지")
    st.caption("개발 메모를 정리해 이미지와 함께 Notion에 발행합니다.")
    st.divider()
    devlog_flow.run()
