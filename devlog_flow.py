"""개발 일지 모드 — 메모/마크다운을 다듬어 Notion·네이버에 올린다.

- 저장된 DEVLOG.md를 불러오거나 직접 메모를 쓰고
- 수정 요청(피드백)으로 다듬고 (되돌리기 가능)
- 스크린샷/사진과 함께 Notion에 원클릭 발행
- 네이버 블로그용 깔끔한 텍스트로 복사

발행 위치: NOTION_DEVLOG_PARENT_ID (없으면 NOTION_PARENT_ID로 발행)
"""
import os
from datetime import date

import streamlit as st

import notion_agent
from core import writer
from core import draft

DEVLOG_PATH = os.path.join(os.path.dirname(__file__), "DEVLOG.md")


def _devlog_parent():
    return os.environ.get("NOTION_DEVLOG_PARENT_ID", "").strip()


def _naver_text(md):
    """마크다운 기호를 정리해 네이버에 붙여넣기 좋은 평문으로."""
    out = []
    for raw in (md or "").splitlines():
        s = raw.rstrip().replace("**", "")
        t = s.strip()
        if t in ("---", "___", "***"):
            out.append("")
        elif t.startswith("### "):
            out.append(t[4:])
        elif t.startswith("## "):
            out.append("■ " + t[3:])
        elif t.startswith("# "):
            out.append(t[2:])
        elif t.startswith(("- ", "* ")):
            out.append("• " + t[2:])
        elif t.startswith("> "):
            out.append("“" + t[2:] + "”")
        else:
            out.append(s)
    return "\n".join(out).strip()


def run():
    # 위젯이 그려지기 전에 처리해야 하는 상태 변경 (Streamlit 제약)
    if st.session_state.pop("dv_clear", False):
        st.session_state.pop("dv_text_in", None)
        st.session_state.pop("dv_text_prev", None)
        st.session_state.dv_url = ""
        draft.clear("devlog")

    # 진행 상태 자동 저장 (네트워크 끊김 복구용)
    if (st.session_state.get("dv_text_in") or "").strip():
        draft.save("devlog", {
            "dv_text_in": st.session_state.dv_text_in,
            "dv_text_prev": st.session_state.get("dv_text_prev", ""),
            "dv_url": st.session_state.get("dv_url", ""),
            "step": "d0",
        })

    st.markdown('<div class="step-pill">📓 개발 일지</div>', unsafe_allow_html=True)

    if not notion_agent.has_credentials():
        st.info("Notion 발행에는 NOTION_TOKEN / NOTION_PARENT_ID 설정이 필요합니다. "
                "(DEPLOY.md 참고) — 네이버 붙여넣기는 설정 없이도 됩니다.")
    elif not _devlog_parent():
        st.warning("NOTION_DEVLOG_PARENT_ID 가 설정돼 있지 않아 운동일지와 같은 위치"
                   "(NOTION_PARENT_ID)에 올라갑니다. 개발일지 전용 페이지에 올리려면 "
                   "그 페이지 ID를 Secrets에 추가하세요.")

    title = st.text_input("제목", value=f"AI 개발 일지 — {date.today():%Y-%m-%d}")

    # ── 모든 본문 변경은 text_area가 그려지기 전에 처리한다 ──
    prev_text = st.session_state.get("dv_text_in", "")

    c1, c2 = st.columns(2)
    with c1:
        load_clicked = (os.path.exists(DEVLOG_PATH) and
                        st.button("📜 저장된 개발일지 불러오기", use_container_width=True))
    with c2:
        polish_clicked = st.button("✨ AI로 다듬기", use_container_width=True,
                                   disabled=not prev_text.strip(),
                                   help="거친 메모를 일지 형태로 '전체 재구성'합니다. "
                                        "이미 완성된 글에는 쓰지 마세요.")
        st.caption("✨ 다듬기 = 전체 재구성 (메모용)")

    fb = st.text_input("✏️ 수정 요청 (예: '2일차 인코딩 문제를 더 자세히', '더 짧게')",
                       key="dv_fb")
    c3, c4 = st.columns(2)
    with c3:
        revise_clicked = st.button("✏️ 수정 요청 반영", use_container_width=True,
                                   disabled=not (prev_text.strip() and fb.strip()),
                                   help="지금 글은 그대로 두고 요청한 부분만 고칩니다.")
        st.caption("✏️ 수정 = 지금 글 유지 + 요청만 반영")
    with c4:
        undo_clicked = st.button("↩️ 이전 버전과 바꾸기", use_container_width=True,
                                 disabled=not st.session_state.get("dv_text_prev"),
                                 help="수정 전/후 버전을 서로 맞바꿉니다. 다시 누르면 원복됩니다.")

    if load_clicked:
        st.session_state.dv_text_in = open(DEVLOG_PATH, encoding="utf-8").read()
        st.rerun()
    elif polish_clicked:
        st.session_state.dv_text_prev = prev_text
        with st.spinner("다듬는 중..."):
            st.session_state.dv_text_in = writer.generate(
                f"""다음 개발 메모를 Notion에 올릴 개발 일지로 다듬어주세요.
마크다운(#, ##, -, >)으로 구조를 잡고, 날짜별 항목은 순서를 유지하세요.
없는 사실을 지어내지 말고, 다듬어진 일지 본문만 출력하세요.

{prev_text}""", max_tokens=max(3000, min(8000, len(prev_text) + 500)))
        st.rerun()
    elif revise_clicked:
        st.session_state.dv_text_prev = prev_text
        with st.spinner("수정 중..."):
            st.session_state.dv_text_in = writer.revise_with_feedback(
                "개발 일지(마크다운)", prev_text, fb,
                "마크다운 구조(#, ##, -, >)는 유지하세요.")
        st.rerun()
    elif undo_clicked:
        # 두 버전을 맞바꿔서 언제든 다시 되돌릴 수 있게 (토글)
        st.session_state.dv_text_in = st.session_state.dv_text_prev
        st.session_state.dv_text_prev = prev_text
        st.rerun()

    txt = st.text_area("내용 (마크다운 지원: #, ##, -, >, ---)", key="dv_text_in",
                       height=340,
                       placeholder="오늘 한 개발 작업을 메모하거나, 위 버튼으로 저장된 개발일지를 불러오세요.")

    # ── 네이버 붙여넣기 ─────────────────────────────────────
    if (txt or "").strip():
        with st.expander("📋 네이버 블로그에 붙여넣기"):
            st.caption("아래 상자 오른쪽 위 복사 아이콘을 눌러 네이버 글쓰기에 붙여넣으세요. "
                       "(마크다운 기호를 정리한 깔끔한 텍스트)")
            st.code(_naver_text(txt), language=None)

    # ── Notion 발행 ────────────────────────────────────────
    photos = st.file_uploader("📷 함께 올릴 이미지 (스크린샷 등, 선택 · 여러 장 가능)",
                              accept_multiple_files=True,
                              type=["png", "jpg", "jpeg", "gif", "webp"],
                              key="dv_photos")

    st.write("")
    if st.session_state.get("dv_url"):
        st.success("✅ Notion에 발행됨!")
        st.link_button("🔗 Notion에서 열기", st.session_state.dv_url)
        if st.button("🆕 새 일지 쓰기"):
            st.session_state.dv_clear = True
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
