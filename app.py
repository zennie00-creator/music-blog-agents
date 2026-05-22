import streamlit as st
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))

import anthropic
from curation_agent import chat_curation, get_album_versions
from info_agent import get_music_info
from audio_agent import get_audio_info
from image_agent import get_album_art, get_artist_image

PROFILE_PATH = os.path.join(os.path.dirname(__file__), "audio_profile.json")

# ── 페이지 설정 ──────────────────────────────────────────
st.set_page_config(page_title="음악 블로그 에이전트", page_icon="🎼", layout="centered")

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
    "step": 0,
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
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── 오디오 프로필 로드/저장 ───────────────────────────────
def load_profile():
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"devices": "", "room": "", "preferences": "", "notes": ""}

def save_profile(p):
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)

# ── 사이드바: 오디오 프로필 설정 ─────────────────────────
with st.sidebar:
    st.markdown("### 🎧 나의 오디오 환경")
    st.caption("저장해두면 청취 가이드가 내 환경에 맞게 작성됩니다.")
    p = load_profile()
    devices     = st.text_area("청취 기기", value=p.get("devices",""),
                    placeholder="예: Sony WH-1000XM5 헤드폰, Sonos Era 300 스피커")
    room        = st.text_input("청취 공간", value=p.get("room",""),
                    placeholder="예: 15평 거실, 작은 서재, 통근 지하철")
    preferences = st.text_area("청취 성향", value=p.get("preferences",""),
                    placeholder="예: 저음 풍부한 걸 좋아함, 보컬이 선명하게 들리길 원함")
    notes       = st.text_input("기타", value=p.get("notes",""),
                    placeholder="예: 이퀄라이저 Flat 세팅 사용")
    if st.button("💾 저장", use_container_width=True):
        save_profile({"devices": devices, "room": room,
                      "preferences": preferences, "notes": notes})
        st.success("저장됐습니다!")

# ── 헬퍼 ─────────────────────────────────────────────────
def revise_with_feedback(content_type, original, feedback, song):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model="claude-opus-4-6", max_tokens=1500,
        messages=[{"role": "user", "content":
            f"""다음 {content_type} 내용을 사용자 피드백에 맞게 수정해주세요.
음악: {song.get('artist','')} - {song.get('track','')} ({song.get('album','')})

[원본]
{original}

[사용자 피드백]
{feedback}

같은 형식과 분량을 유지하면서 피드백을 반영해주세요."""}]
    )
    return msg.content[0].text

def display_chat(history):
    for m in history:
        content = m["content"]
        if m["role"] == "assistant" and "[SONGS]" in content:
            content = content.split("[SONGS]")[0].strip()
        with st.chat_message("assistant" if m["role"] == "assistant" else "user"):
            st.markdown(content)

def show_images():
    """세션에 저장된 이미지 표시"""
    artist_img = st.session_state.get("artist_img")
    album_art  = st.session_state.get("album_art")
    if not artist_img and not album_art:
        return
    cols = st.columns(2)
    with cols[0]:
        if artist_img:
            st.image(artist_img, use_container_width=True)
            st.markdown('<div class="img-label">아티스트</div>', unsafe_allow_html=True)
    with cols[1]:
        if album_art:
            st.image(album_art, use_container_width=True)
            st.markdown('<div class="img-label">앨범 아트</div>', unsafe_allow_html=True)

def fetch_images(artist, album):
    """이미지를 가져와 세션에 저장"""
    st.session_state.artist_img = get_artist_image(artist)
    st.session_state.album_art  = get_album_art(artist, album)

def make_naver_html(song, blog_text, artist_img, album_art):
    """네이버 블로그에 바로 붙여넣기 가능한 HTML 생성"""
    img_section = ""
    if artist_img or album_art:
        img_cols = ""
        if artist_img:
            img_cols += f'<td style="padding:8px;text-align:center;"><img src="{artist_img}" width="240" style="border-radius:8px;"/><br/><span style="font-size:12px;color:#999;">아티스트</span></td>'
        if album_art:
            img_cols += f'<td style="padding:8px;text-align:center;"><img src="{album_art}" width="240" style="border-radius:8px;"/><br/><span style="font-size:12px;color:#999;">앨범</span></td>'
        img_section = f'<table style="margin:0 auto 24px;border:none;"><tr>{img_cols}</tr></table>'

    version_note = f'<p style="color:#888;font-size:13px;margin:0 0 20px;">({song.get("version_info","")})</p>' if song.get("version_info") else ""

    paragraphs = "".join(
        f'<p style="margin:0 0 1.4em;line-height:1.9;">{p.strip()}</p>'
        for p in blog_text.strip().split("\n\n") if p.strip()
    )

    return f"""<div style="max-width:680px;margin:0 auto;font-family:'나눔명조','Nanum Myeongjo',Georgia,serif;font-size:16px;color:#2c2c2c;">
{img_section}
<h2 style="font-size:20px;font-weight:700;margin:0 0 6px;">{song.get('artist','')} — {song.get('track','')}</h2>
<p style="color:#888;font-size:13px;margin:0 0 4px;">💿 {song.get('album','')}</p>
{version_note}
<hr style="border:none;border-top:1px solid #e9e3d0;margin:20px 0;"/>
{paragraphs}
</div>"""

# ══════════════════════════════════════════════════════════
# STEP 0: 시작
# ══════════════════════════════════════════════════════════
st.title("🎼 음악 블로그 에이전트")
st.caption("분위기나 키워드를 입력하면 단계별로 함께 블로그 글을 완성해 드립니다.")
st.divider()

if st.session_state.step == 0:
    mood_input = st.text_input(
        "오늘의 분위기나 키워드",
        placeholder="예: 피곤한 일요일 오후, 설레는 봄 아침, 비 오는 밤..."
    )
    if st.button("시작하기 →", type="primary", disabled=not mood_input.strip()):
        st.session_state.mood = mood_input.strip()
        st.session_state.step = 1
        st.rerun()

# ══════════════════════════════════════════════════════════
# STEP 1: 큐레이션 (대화형)
# ══════════════════════════════════════════════════════════
elif st.session_state.step == 1:
    st.markdown('<div class="step-pill">🎵 1단계 — 음악 선정</div>', unsafe_allow_html=True)
    st.markdown(f"**키워드:** {st.session_state.mood}")
    st.write("")

    if not st.session_state.chat_history:
        with st.spinner("큐레이터가 준비 중..."):
            response, options = chat_curation(st.session_state.mood, [])
            st.session_state.chat_history = [
                {"role": "user",      "content": f"오늘의 분위기/키워드: {st.session_state.mood}"},
                {"role": "assistant", "content": response},
            ]
            st.session_state.current_options = options
        st.rerun()

    display_chat(st.session_state.chat_history)

    if st.session_state.current_options:
        st.write("")
        st.markdown("**마음에 드는 곡을 선택하거나, 아래 채팅으로 피드백을 주세요:**")
        for i, opt in enumerate(st.session_state.current_options):
            col_card, col_btn = st.columns([5, 1])
            with col_card:
                st.markdown(f"""<div class="song-card">
<div class="song-title">🎵 {opt.get('artist','')} — {opt.get('track','')}</div>
<div class="song-meta">💿 {opt.get('album','')} &nbsp;|&nbsp; {opt.get('genre','')}</div>
<div class="song-reason">{opt.get('reason','')}</div>
</div>""", unsafe_allow_html=True)
            with col_btn:
                st.write("")
                st.write("")
                if st.button("선택", key=f"pick_{i}", type="primary"):
                    st.session_state.pending_song = opt
                    # 아티스트 이미지는 미리 로드, 앨범 아트는 최종 앨범 선택 후 업데이트
                    st.session_state.artist_img = get_artist_image(opt.get("artist",""))
                    st.session_state.album_art  = None
                    st.session_state.step = "1b"
                    st.rerun()
        st.write("")

    user_input = st.chat_input("답변 또는 피드백을 입력하세요...")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.spinner("큐레이터가 생각 중..."):
            response, options = chat_curation(
                st.session_state.mood, st.session_state.chat_history)
        st.session_state.chat_history.append({"role": "assistant", "content": response})
        if options:
            st.session_state.current_options = options
        st.rerun()

# ══════════════════════════════════════════════════════════
# STEP 1b: 앨범 버전 선택 (모든 장르)
# ══════════════════════════════════════════════════════════
elif st.session_state.step == "1b":
    pending = st.session_state.pending_song
    genre   = pending.get("genre", "non-classical")
    artist  = pending.get("artist", "")
    track   = pending.get("track", "")

    st.markdown('<div class="step-pill">💿 1-2단계 — 앨범 선택</div>', unsafe_allow_html=True)
    st.markdown(f"**선정 곡:** {artist} — {track}")
    if genre == "classical":
        st.caption("같은 작품도 연주자/지휘자에 따라 느낌이 다릅니다. 원하는 음반을 골라주세요.")
    else:
        st.caption("이 곡이 수록된 여러 앨범/버전입니다. 원하는 버전을 골라주세요.")
    st.write("")

    # 아티스트 이미지 표시 (앨범 아트는 아직 미선택)
    if st.session_state.artist_img:
        col1, col2 = st.columns(2)
        with col1:
            st.image(st.session_state.artist_img, use_container_width=True)
            st.markdown('<div class="img-label">아티스트</div>', unsafe_allow_html=True)
        with col2:
            st.markdown("**앨범을 선택하면**\n앨범 아트가 표시됩니다.", unsafe_allow_html=False)
        st.write("")

    if not st.session_state.album_versions:
        with st.spinner("앨범 버전을 찾는 중..."):
            st.session_state.album_versions = get_album_versions(artist, track, genre)
        st.rerun()

    for i, ver in enumerate(st.session_state.album_versions):
        col_card, col_btn = st.columns([5, 1])
        with col_card:
            st.markdown(f"""<div class="song-card">
<div class="song-title">💿 {ver.get('album','')}</div>
<div class="song-meta">{ver.get('version_info','')}</div>
<div class="song-reason">{ver.get('feature','')}</div>
</div>""", unsafe_allow_html=True)
        with col_btn:
            st.write("")
            st.write("")
            if st.button("선택", key=f"ver_{i}", type="primary"):
                song = dict(pending)
                selected_album = ver.get("album", pending.get("album", ""))
                song["album"]        = selected_album
                song["version_info"] = ver.get("version_info", "")
                st.session_state.song = song
                # 선택된 앨범으로 앨범 아트 업데이트
                with st.spinner("앨범 아트 로딩 중..."):
                    st.session_state.album_art = get_album_art(artist, selected_album, track)
                st.session_state.step = 2
                st.rerun()

    st.write("")
    if st.button("← 곡 다시 선택"):
        st.session_state.album_versions = []
        st.session_state.pending_song = {}
        st.session_state.artist_img = None
        st.session_state.step = 1
        st.rerun()

# ══════════════════════════════════════════════════════════
# STEP 2: 음악 정보
# ══════════════════════════════════════════════════════════
elif st.session_state.step == 2:
    song = st.session_state.song
    st.markdown('<div class="step-pill">📖 2단계 — 음악 정보</div>', unsafe_allow_html=True)
    st.markdown(f"**선정 곡:** {song.get('artist','')} — {song.get('track','')} ({song.get('album','')})")
    st.write("")

    show_images()
    st.write("")

    if not st.session_state.info:
        with st.spinner("음악 정보를 수집하는 중..."):
            track_desc = song.get("track", "")
            if song.get("version_info"):
                track_desc = f"{track_desc} [{song['version_info']}]"
            st.session_state.info = get_music_info(
                song.get("artist",""), song.get("album",""), track_desc)
        st.rerun()

    st.markdown('<div class="section-label">음악 정보 초안</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="content-box">{st.session_state.info}</div>', unsafe_allow_html=True)
    st.write("")

    feedback = st.text_input("수정 요청 (없으면 비워두고 다음으로)", key="info_fb",
        placeholder="예: 더 짧게, 시대적 배경을 더 자세히, 더 쉬운 말로...")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✏️ 수정 요청", disabled=not feedback.strip()):
            with st.spinner("수정 중..."):
                st.session_state.info = revise_with_feedback(
                    "음악 정보", st.session_state.info, feedback, song)
            st.rerun()
    with col2:
        if st.button("다음 단계로 →", type="primary"):
            st.session_state.step = 3
            st.rerun()

# ══════════════════════════════════════════════════════════
# STEP 3: 오디오 가이드
# ══════════════════════════════════════════════════════════
elif st.session_state.step == 3:
    song = st.session_state.song
    st.markdown('<div class="step-pill">🔊 3단계 — 청취 가이드</div>', unsafe_allow_html=True)
    st.markdown(f"**선정 곡:** {song.get('artist','')} — {song.get('track','')} ({song.get('album','')})")
    st.write("")

    p = load_profile()
    if any(p.get(k) for k in ("devices","room","preferences","notes")):
        st.info(f"🎧 오디오 환경 반영 중: {p.get('devices','')} / {p.get('room','')}")

    if not st.session_state.audio:
        with st.spinner("청취 가이드를 작성하는 중..."):
            st.session_state.audio = get_audio_info(
                song.get("artist",""), song.get("album",""), song.get("track",""))
        st.rerun()

    st.markdown('<div class="section-label">청취 가이드 초안</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="content-box">{st.session_state.audio}</div>', unsafe_allow_html=True)
    st.write("")

    feedback = st.text_input("수정 요청 (없으면 비워두고 다음으로)", key="audio_fb",
        placeholder="예: 더 감성적으로, 추천 환경을 더 구체적으로...")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✏️ 수정 요청", disabled=not feedback.strip()):
            with st.spinner("수정 중..."):
                st.session_state.audio = revise_with_feedback(
                    "청취 가이드", st.session_state.audio, feedback, song)
            st.rerun()
    with col2:
        if st.button("다음 단계로 →", type="primary"):
            st.session_state.step = 4
            st.rerun()

# ══════════════════════════════════════════════════════════
# STEP 4: 블로그 글
# ══════════════════════════════════════════════════════════
elif st.session_state.step == 4:
    song = st.session_state.song
    st.markdown('<div class="step-pill">✍️ 4단계 — 블로그 글 작성</div>', unsafe_allow_html=True)
    st.markdown(f"**선정 곡:** {song.get('artist','')} — {song.get('track','')} ({song.get('album','')})")
    st.write("")

    if not st.session_state.blog:
        with st.spinner("블로그 글을 작성하는 중..."):
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            version_note = f"\n음반 버전: {song['version_info']}" if song.get("version_info") else ""
            prompt = f"""당신은 감성적인 음악 블로그 작가입니다.
오늘의 테마: {st.session_state.mood}
추천 음악: {song['artist']} - {song['track']} ({song['album']}){version_note}
[음악 배경 정보] {st.session_state.info}
[오디오 청취 가이드] {st.session_state.audio}
700~900자 에세이 스타일로, 소제목 없이 자연스럽게 써주세요.
마지막은 독자에게 지금 이 음악을 틀어보라는 권유로 마무리해주세요."""
            msg = client.messages.create(
                model="claude-opus-4-6", max_tokens=1500,
                messages=[{"role": "user", "content": prompt}])
            st.session_state.blog = msg.content[0].text
        st.rerun()

    show_images()
    st.write("")
    st.markdown('<div class="section-label">블로그 글 초안</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="content-box">{st.session_state.blog}</div>', unsafe_allow_html=True)
    st.write("")

    feedback = st.text_input("수정 요청 (없으면 비워두고 완성)", key="blog_fb",
        placeholder="예: 더 감성적으로, 첫 문단을 바꿔줘, 마무리를 다르게...")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("✏️ 수정 요청", disabled=not feedback.strip()):
            with st.spinner("수정 중..."):
                st.session_state.blog = revise_with_feedback(
                    "블로그 글", st.session_state.blog, feedback, song)
            st.rerun()
    with col2:
        if st.button("✅ 완성 & 저장", type="primary"):
            fname = f"blog_{song['artist'].replace(' ', '_')}.txt"
            fpath = os.path.join(os.path.dirname(__file__), fname)
            naver_html = make_naver_html(
                song, st.session_state.blog,
                st.session_state.artist_img, st.session_state.album_art)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(f"[테마: {st.session_state.mood}]\n[음악: {song['artist']} - {song['track']}]\n\n{st.session_state.blog}")
            html_fname = fname.replace(".txt", "_naver.html")
            html_fpath = os.path.join(os.path.dirname(__file__), html_fname)
            with open(html_fpath, "w", encoding="utf-8") as f:
                f.write(naver_html)
            st.success(f"💾 저장 완료!")

            tab1, tab2 = st.tabs(["📄 텍스트 다운로드", "🟢 네이버 블로그 HTML"])
            with tab1:
                st.download_button("📥 텍스트 다운로드", data=st.session_state.blog,
                    file_name=fname, mime="text/plain")
            with tab2:
                st.caption("아래 HTML을 복사해서 네이버 블로그 → 글쓰기 → HTML 편집기에 붙여넣으세요.")
                st.code(naver_html, language="html")
                st.download_button("📥 HTML 다운로드", data=naver_html,
                    file_name=html_fname, mime="text/html")
    with col3:
        if st.button("↩️ 처음부터"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
