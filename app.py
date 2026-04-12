import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from curation_agent import curate_music
from info_agent import get_music_info
from audio_agent import get_audio_info
import anthropic

st.set_page_config(page_title="음악 블로그 에이전트", page_icon="🎼", layout="centered")

st.markdown("""
<style>
    .main { max-width: 760px; }
    .step-box {
        background: #f8f9fa;
        border-left: 4px solid #6c757d;
        padding: 12px 16px;
        margin: 8px 0;
        border-radius: 0 8px 8px 0;
        font-size: 14px;
        color: #495057;
    }
    .step-done {
        border-left-color: #28a745;
        color: #155724;
        background: #d4edda;
    }
    .step-active {
        border-left-color: #007bff;
        color: #004085;
        background: #cce5ff;
    }
    .blog-post {
        background: #fffef7;
        border: 1px solid #e9e3d0;
        border-radius: 12px;
        padding: 32px;
        margin-top: 24px;
        line-height: 1.9;
        font-size: 16px;
        color: #2c2c2c;
    }
    .music-tag {
        display: inline-block;
        background: #343a40;
        color: white;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 13px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🎼 음악 블로그 에이전트")
st.caption("분위기나 키워드를 입력하면 어울리는 음악과 에세이를 써드립니다.")

st.divider()

mood = st.text_input("오늘의 분위기나 키워드", placeholder="예: 피곤한 일요일 오후, 설레는 봄 아침, 비 오는 밤...")

def parse_curation(text):
    r = {"artist": "", "album": "", "track": ""}
    for line in text.strip().split("\n"):
        if "아티스트" in line and ":" in line:
            r["artist"] = line.split(":", 1)[-1].strip()
        elif "앨범" in line and ":" in line:
            r["album"] = line.split(":", 1)[-1].strip()
        elif "트랙" in line and ":" in line:
            r["track"] = line.split(":", 1)[-1].strip()
    return r

if st.button("✍️ 블로그 글 쓰기", type="primary", disabled=not mood.strip()):

    status = st.empty()
    step1 = st.empty()
    step2 = st.empty()
    step3 = st.empty()
    step4 = st.empty()

    try:
        # Step 1
        step1.markdown('<div class="step-box step-active">🎵 [1/4] 큐레이션 매니저 - 음악 선정 중...</div>', unsafe_allow_html=True)
        cur = curate_music(mood)
        m = parse_curation(cur)
        step1.markdown(f'<div class="step-box step-done">✅ [1/4] 선정 완료: {m["artist"]} - {m["track"]}</div>', unsafe_allow_html=True)

        # Step 2
        step2.markdown('<div class="step-box step-active">📖 [2/4] 음악정보 매니저 - 정보 수집 중...</div>', unsafe_allow_html=True)
        info = get_music_info(m["artist"], m["album"], m["track"])
        step2.markdown('<div class="step-box step-done">✅ [2/4] 음악 정보 수집 완료</div>', unsafe_allow_html=True)

        # Step 3
        step3.markdown('<div class="step-box step-active">🔊 [3/4] 오디오 매니저 - 청취 가이드 작성 중...</div>', unsafe_allow_html=True)
        audio = get_audio_info(m["artist"], m["album"], m["track"])
        step3.markdown('<div class="step-box step-done">✅ [3/4] 청취 가이드 완료</div>', unsafe_allow_html=True)

        # Step 4
        step4.markdown('<div class="step-box step-active">✍️ [4/4] 총괄 매니저 - 블로그 글 작성 중...</div>', unsafe_allow_html=True)
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        prompt = f"""당신은 감성적인 음악 블로그 작가입니다.
오늘의 테마: {mood}
추천 음악: {m['artist']} - {m['track']} ({m['album']})
[큐레이션 이유] {cur}
[음악 배경 정보] {info}
[오디오 청취 가이드] {audio}
700~900자 에세이 스타일로, 소제목 없이 자연스럽게 써주세요.
마지막은 독자에게 지금 이 음악을 틀어보라는 권유로 마무리해주세요."""
        msg = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        post = msg.content[0].text
        step4.markdown('<div class="step-box step-done">✅ [4/4] 블로그 글 완성!</div>', unsafe_allow_html=True)

        # Save file
        fname = f"blog_{m['artist'].replace(' ', '_')}.txt"
        fpath = os.path.join(os.path.dirname(__file__), fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(f"[테마: {mood}]\n[음악: {m['artist']} - {m['track']}]\n\n{post}")

        st.divider()
        st.markdown(f'<div class="music-tag">🎵 {m["artist"]} — {m["track"]} ({m["album"]})</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="blog-post">{post.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)

        st.divider()
        col1, col2 = st.columns([3, 1])
        with col1:
            st.caption(f"💾 {fname} 로 저장되었습니다.")
        with col2:
            st.download_button("📥 다운로드", data=post, file_name=fname, mime="text/plain")

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
