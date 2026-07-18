"""음악 모드 Streamlit 흐름 (기존 app.py의 음악 파이프라인을 분리).

STEP 0  : 분위기/키워드 입력
STEP 1  : 큐레이션 (대화형)
STEP 1b : 앨범 버전 선택
STEP 2  : 음악 정보
STEP 3  : 오디오 청취 가이드
STEP 4  : 블로그 글 작성 → 네이버 HTML 저장
"""
import os
import streamlit as st

from curation_agent import chat_curation, get_album_versions
from info_agent import get_music_info
from audio_agent import get_audio_info
from image_agent import get_album_art, get_artist_image

from core import writer
from core.naver_html import build_naver_html, wrap_document


# ── 헬퍼 ─────────────────────────────────────────────────
def _revise(content_type, original, feedback, song):
    ctx = f"음악: {song.get('artist','')} - {song.get('track','')} ({song.get('album','')})"
    return writer.revise_with_feedback(content_type, original, feedback, ctx)


def _display_chat(history):
    for m in history:
        content = m["content"]
        if m["role"] == "assistant" and "[SONGS]" in content:
            content = content.split("[SONGS]")[0].strip()
        with st.chat_message("assistant" if m["role"] == "assistant" else "user"):
            st.markdown(content)


def _show_images():
    artist_img = st.session_state.get("artist_img")
    album_art = st.session_state.get("album_art")
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


def _make_naver_html(song, blog_text, artist_img, album_art):
    return build_naver_html(
        title=f"{song.get('artist','')} — {song.get('track','')}",
        meta_lines=[f"💿 {song.get('album','')}"],
        images=[(artist_img, "아티스트"), (album_art, "앨범")],
        note=song.get("version_info", ""),
        body_text=blog_text,
    )


# ── 흐름 ─────────────────────────────────────────────────
def run():
    step = st.session_state.step

    # STEP 0: 시작
    if step == 0:
        mood_input = st.text_input(
            "오늘의 분위기나 키워드",
            placeholder="예: 피곤한 일요일 오후, 설레는 봄 아침, 비 오는 밤...")
        if st.button("시작하기 →", type="primary", disabled=not mood_input.strip()):
            st.session_state.mood = mood_input.strip()
            st.session_state.step = 1
            st.rerun()

    # STEP 1: 큐레이션 (대화형)
    elif step == 1:
        st.markdown('<div class="step-pill">음악 · 1 / 5 — 음악 선정</div>', unsafe_allow_html=True)
        st.markdown(f"**키워드:** {st.session_state.mood}")
        st.write("")

        if not st.session_state.chat_history:
            with st.spinner("큐레이터가 준비 중..."):
                response, options = chat_curation(st.session_state.mood, [])
                st.session_state.chat_history = [
                    {"role": "user", "content": f"오늘의 분위기/키워드: {st.session_state.mood}"},
                    {"role": "assistant", "content": response},
                ]
                st.session_state.current_options = options
            st.rerun()

        _display_chat(st.session_state.chat_history)

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
                        st.session_state.artist_img = get_artist_image(opt.get("artist", ""))
                        st.session_state.album_art = None
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

    # STEP 1b: 앨범 버전 선택
    elif step == "1b":
        pending = st.session_state.pending_song
        genre = pending.get("genre", "non-classical")
        artist = pending.get("artist", "")
        track = pending.get("track", "")

        st.markdown('<div class="step-pill">음악 · 2 / 5 — 앨범 선택</div>', unsafe_allow_html=True)
        st.markdown(f"**선정 곡:** {artist} — {track}")
        if genre == "classical":
            st.caption("같은 작품도 연주자/지휘자에 따라 느낌이 다릅니다. 원하는 음반을 골라주세요.")
        else:
            st.caption("이 곡이 수록된 여러 앨범/버전입니다. 원하는 버전을 골라주세요.")
        st.write("")

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
                    song["album"] = selected_album
                    song["version_info"] = ver.get("version_info", "")
                    st.session_state.song = song
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

    # STEP 2: 음악 정보
    elif step == 2:
        song = st.session_state.song
        st.markdown('<div class="step-pill">음악 · 3 / 5 — 음악 정보</div>', unsafe_allow_html=True)
        st.markdown(f"**선정 곡:** {song.get('artist','')} — {song.get('track','')} ({song.get('album','')})")
        st.write("")

        _show_images()
        st.write("")

        if not st.session_state.info:
            with st.spinner("음악 정보를 수집하는 중..."):
                track_desc = song.get("track", "")
                if song.get("version_info"):
                    track_desc = f"{track_desc} [{song['version_info']}]"
                st.session_state.info = get_music_info(
                    song.get("artist", ""), song.get("album", ""), track_desc)
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
                    st.session_state.info = _revise(
                        "음악 정보", st.session_state.info, feedback, song)
                st.rerun()
        with col2:
            if st.button("다음 단계로 →", type="primary"):
                st.session_state.step = 3
                st.rerun()

    # STEP 3: 오디오 가이드
    elif step == 3:
        song = st.session_state.song
        st.markdown('<div class="step-pill">음악 · 4 / 5 — 청취 가이드</div>', unsafe_allow_html=True)
        st.markdown(f"**선정 곡:** {song.get('artist','')} — {song.get('track','')} ({song.get('album','')})")
        st.write("")

        from core import profile as profile_store
        p = profile_store.load(profile_store.AUDIO_PROFILE, profile_store.AUDIO_DEFAULT)
        if any(p.get(k) for k in ("devices", "room", "preferences", "notes")):
            st.info(f"🎧 오디오 환경 반영 중: {p.get('devices','')} / {p.get('room','')}")

        if not st.session_state.audio:
            with st.spinner("청취 가이드를 작성하는 중..."):
                st.session_state.audio = get_audio_info(
                    song.get("artist", ""), song.get("album", ""), song.get("track", ""))
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
                    st.session_state.audio = _revise(
                        "청취 가이드", st.session_state.audio, feedback, song)
                st.rerun()
        with col2:
            if st.button("다음 단계로 →", type="primary"):
                st.session_state.step = 4
                st.rerun()

    # STEP 4: 블로그 글
    elif step == 4:
        song = st.session_state.song
        st.markdown('<div class="step-pill">음악 · 5 / 5 — 블로그 글 작성</div>', unsafe_allow_html=True)
        st.markdown(f"**선정 곡:** {song.get('artist','')} — {song.get('track','')} ({song.get('album','')})")
        st.write("")

        if not st.session_state.blog:
            with st.spinner("블로그 글을 작성하는 중..."):
                version_note = f"\n음반 버전: {song['version_info']}" if song.get("version_info") else ""
                prompt = f"""당신은 감성적인 음악 블로그 작가입니다.
오늘의 테마: {st.session_state.mood}
추천 음악: {song['artist']} - {song['track']} ({song['album']}){version_note}
[음악 배경 정보] {st.session_state.info}
[오디오 청취 가이드] {st.session_state.audio}
700~900자 에세이 스타일로, 소제목 없이 자연스럽게 써주세요.
마지막은 독자에게 지금 이 음악을 틀어보라는 권유로 마무리해주세요."""
                st.session_state.blog = writer.generate(prompt)
            st.rerun()

        _show_images()
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
                    st.session_state.blog = _revise(
                        "블로그 글", st.session_state.blog, feedback, song)
                st.rerun()
        with col2:
            if st.button("✅ 완성 & 저장", type="primary"):
                fname = f"blog_{song['artist'].replace(' ', '_')}.txt"
                fpath = os.path.join(os.path.dirname(__file__), fname)
                naver_html = _make_naver_html(
                    song, st.session_state.blog,
                    st.session_state.artist_img, st.session_state.album_art)
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(f"[테마: {st.session_state.mood}]\n[음악: {song['artist']} - {song['track']}]\n\n{st.session_state.blog}")
                html_fname = fname.replace(".txt", "_naver.html")
                with open(os.path.join(os.path.dirname(__file__), html_fname), "w", encoding="utf-8") as f:
                    f.write(naver_html)
                st.session_state.blog_saved_html = naver_html
                st.session_state.blog_saved_names = (fname, html_fname)
                st.success("💾 저장 완료!")
        with col3:
            if st.button("↩️ 처음부터"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

        if st.session_state.get("blog_saved_html"):
            fname, html_fname = st.session_state.blog_saved_names
            plain_lines = [f"{song.get('artist','')} — {song.get('track','')}",
                           f"💿 {song.get('album','')}"]
            if song.get("version_info"):
                plain_lines.append(f"({song['version_info']})")
            plain_lines += ["", st.session_state.blog.strip()]
            plain = "\n".join(plain_lines)

            tab1, tab2, tab3 = st.tabs(
                ["📋 네이버에 붙여넣기 (추천)", "📥 다운로드", "🟢 HTML (고급)"])
            with tab1:
                st.caption("아래 상자 오른쪽 위 복사 아이콘을 누르고, 네이버 글쓰기 화면에 그대로 붙여넣으세요. "
                           "서식 없이 깔끔하게 들어갑니다. (사진은 네이버에서 직접 추가)")
                st.code(plain, language=None)
            with tab2:
                st.download_button("📥 텍스트 파일 다운로드", data=plain,
                    file_name=fname, mime="text/plain")
                st.download_button("📥 HTML 파일 다운로드",
                    data=wrap_document(st.session_state.blog_saved_html,
                                       f"{song.get('artist','')} - {song.get('track','')}"),
                    file_name=html_fname, mime="text/html")
            with tab3:
                st.caption("네이버 새 에디터는 HTML 직접 붙여넣기를 지원하지 않습니다. "
                           "표/이미지까지 살리고 싶으면: HTML 파일 다운로드→브라우저로 열기→"
                           "화면 전체 선택·복사→네이버에 붙여넣으면 서식이 어느 정도 유지됩니다.")
                st.code(st.session_state.blog_saved_html, language="html")
