"""개발 일지 모드 — 메모/마크다운을 Notion '개발일지' 페이지에 자동 발행.

- 저장된 DEVLOG.md를 불러오거나 직접 메모를 쓰고
- 필요하면 AI로 다듬은 뒤
- 스크린샷/사진과 함께 Notion에 원클릭 발행

발행 위치: NOTION_DEVLOG_PARENT_ID (없으면 NOTION_PARENT_ID로 발행)
"""
import os
from datetime import date

import streamlit as st

import notion_agent
from core import writer

DEVLOG_PATH = os.path.join(os.path.dirname(__file__), "DEVLOG.md")


def _devlog_parent():
    return os.environ.get("NOTION_DEVLOG_PARENT_ID", "").strip()


def run():
    st.markdown('<div class="step-pill">📓 개발 일지</div>', unsafe_allow_html=True)

    if not notion_agent.has_credentials():
        st.info("Notion 발행에는 NOTION_TOKEN / NOTION_PARENT_ID 설정이 필요합니다. "
                "(DEPLOY.md 참고)")
    elif not _devlog_parent():
        st.warning("NOTION_DEVLOG_PARENT_ID 가 설정돼 있지 않아 운동일지와 같은 위치"
                   "(NOTION_PARENT_ID)에 올라갑니다. 개발일지 전용 페이지에 올리려면 "
                   "그 페이지 ID를 Secrets에 추가하세요.")

    title = st.text_input("제목", value=f"AI 개발 일지 — {date.today():%Y-%m-%d}")
    txt = st.text_area("내용 (마크다운 지원: #, ##, -, >, ---)", key="dv_text_in",
                       height=340,
                       placeholder="오늘 한 개발 작업을 메모하거나, 아래 버튼으로 저장된 개발일지를 불러오세요.")

    c1, c2 = st.columns(2)
    with c1:
        if os.path.exists(DEVLOG_PATH):
            if st.button("📜 저장된 개발일지(DEVLOG.md) 불러오기", use_container_width=True):
                with open(DEVLOG_PATH, encoding="utf-8") as f:
                    st.session_state.dv_text_in = f.read()
                st.rerun()
    with c2:
        if st.button("✨ AI로 다듬기", use_container_width=True,
                     disabled=not (txt or "").strip()):
            with st.spinner("다듬는 중..."):
                st.session_state.dv_text_in = writer.generate(
                    f"""다음 개발 메모를 Notion에 올릴 개발 일지로 다듬어주세요.
마크다운(#, ##, -, >)으로 구조를 잡고, 날짜별 항목은 순서를 유지하세요.
없는 사실을 지어내지 말고, 다듬어진 일지 본문만 출력하세요.

{txt}""", max_tokens=3000)
            st.rerun()

    photos = st.file_uploader("📷 함께 올릴 이미지 (스크린샷 등, 선택 · 여러 장 가능)",
                              accept_multiple_files=True,
                              type=["png", "jpg", "jpeg", "gif", "webp"],
                              key="dv_photos")

    st.write("")
    if st.session_state.get("dv_url"):
        st.success("✅ Notion에 발행됨!")
        st.link_button("🔗 Notion에서 열기", st.session_state.dv_url)
        if st.button("🆕 새 일지 쓰기"):
            st.session_state.dv_url = ""
            st.session_state.dv_text_in = ""
            st.rerun()
        return

    if st.button("📝 Notion에 올리기", type="primary",
                 disabled=not ((txt or "").strip() and notion_agent.has_credentials())):
        with st.spinner("Notion에 글을 만드는 중..."):
            try:
                image_ids = []
                for f in (photos or []):
                    try:
                        image_ids.append(
                            notion_agent.upload_image(f.getvalue(), f.name, f.type))
                    except Exception as e:
                        st.warning(f"이미지 업로드 실패: {f.name} — {e}")
                blocks = notion_agent.md_blocks(txt)
                if image_ids:
                    blocks.append(notion_agent._divider())
                    blocks.append(notion_agent._heading("📸 이미지"))
                    blocks += [notion_agent.image_upload_block(i) for i in image_ids]
                url = notion_agent.create_page(
                    (title or "").strip() or "개발 일지", blocks,
                    parent_id=_devlog_parent() or None, icon="🛠")
                st.session_state.dv_url = url
                st.rerun()
            except Exception as e:
                st.error(f"발행 실패: {e}")
