"""운동 모드 Streamlit 흐름 (하루 여러 운동 멀티 선택 + 편집 지원).

STEP w0 : 오늘 운동 불러오기 (Whoop) + 여러 운동 체크박스 선택
STEP w1 : 종목명·거리 편집 + 운동 전후 기분·몸 상태 입력
STEP w2 : 분석 + 운동 일지 초안 → 수정 → 네이버 HTML 저장
"""
import os
import streamlit as st

import whoop_agent
import workout_agent
import notion_agent
from core import writer
from core.naver_html import build_naver_html, wrap_document
from core import profile as profile_store


def _profile():
    return profile_store.load(profile_store.WORKOUT_PROFILE, profile_store.WORKOUT_DEFAULT)


def _zone_bar_html(w):
    """존별 체류시간을 가로 스택 막대로. 존 데이터 없으면 빈 문자열."""
    zones = w.get("zones") or {}
    total = sum(v for v in zones.values() if v)
    if not total:
        return ""
    segs = ""
    for k in sorted(zones):
        v = zones[k]
        if not v:
            continue
        pct = v / total * 100
        color = workout_agent.ZONE_COLORS.get(k, "#999")
        segs += (f'<div style="width:{pct:.1f}%;background:{color};" '
                 f'title="{workout_agent.ZONE_LABELS.get(k, k)} {v}분"></div>')
    return (f'<div style="margin:10px 0 2px;font-size:13px;color:#868e96;">'
            f'{workout_agent.sport_emoji(w.get("sport"))} {w.get("sport","")} — 심박존 분포</div>'
            f'<div style="display:flex;height:14px;border-radius:7px;overflow:hidden;">{segs}</div>'
            f'<div style="font-size:12px;color:#adb5bd;margin-top:3px;">{workout_agent.zone_line(w)}</div>')


def _card(w, unscored=False):
    """운동 한 건을 카드로 표시."""
    meta = []
    if w.get("strain") is not None:
        meta.append(f"Strain {w['strain']}")
    if w.get("avg_hr"):
        meta.append(f"평균 {w['avg_hr']}bpm")
    if w.get("kcal"):
        meta.append(f"{w['kcal']}kcal")
    meta_line = " &nbsp;|&nbsp; ".join(meta) if meta else "상세 데이터 없음"
    tag = ' <span style="color:#e8590c;">· 점수 없음</span>' if unscored else ""
    st.markdown(f"""<div class="song-card">
<div class="song-title">🏃 {w.get('sport','운동')} · {w.get('duration_min','?')}분{tag}</div>
<div class="song-meta">🕒 {w.get('local_time','')} &nbsp;|&nbsp; {meta_line}</div>
</div>""", unsafe_allow_html=True)


def run():
    step = st.session_state.step

    # ── STEP w0: 운동 불러오기 + 멀티 선택 ───────────────────
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
            st.info("ℹ️ Whoop 미연결 상태 — 데모(샘플) 운동 데이터로 흐름을 보여드립니다.")

        st.write("")
        if not st.session_state.wk_workouts:
            if st.button("📥 오늘 운동 불러오기", type="primary"):
                with st.spinner("Whoop에서 데이터를 가져오는 중..."):
                    st.session_state.wk_workouts = whoop_agent.get_recent_workouts()
                    st.session_state.wk_recovery = whoop_agent.get_latest_recovery()
                st.rerun()
            return

        workouts = st.session_state.wk_workouts
        scored = [(i, w) for i, w in enumerate(workouts) if w.get("scored")]
        unscored = [(i, w) for i, w in enumerate(workouts) if not w.get("scored")]

        st.markdown("**오늘 블로그에 담을 운동을 모두 선택하세요.** (여러 개 선택 가능)")
        st.write("")

        for i, w in scored:
            c1, c2 = st.columns([1, 9])
            with c1:
                st.write("")
                st.checkbox(" ", key=f"pick_wk_{i}", label_visibility="collapsed")
            with c2:
                _card(w)

        if unscored:
            with st.expander(f"점수 없는 기록 {len(unscored)}개 더 보기 "
                             "(짧거나 자동 감지된 활동 — 보통 제외해도 됩니다)"):
                for i, w in unscored:
                    c1, c2 = st.columns([1, 9])
                    with c1:
                        st.write("")
                        st.checkbox(" ", key=f"pick_wk_{i}", label_visibility="collapsed")
                    with c2:
                        _card(w, unscored=True)

        st.write("")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 다시 불러오기"):
                st.session_state.wk_workouts = []
                st.rerun()
        with col2:
            if st.button("선택 완료 →", type="primary"):
                chosen = [w for i, w in enumerate(workouts)
                          if st.session_state.get(f"pick_wk_{i}")]
                if not chosen:
                    st.warning("운동을 하나 이상 선택해주세요.")
                else:
                    # 먼저 한 운동이 운동 1이 되도록 시간 오름차순 정렬
                    chosen.sort(key=lambda w: w.get("start") or "")
                    st.session_state.wk_selected_list = chosen
                    st.session_state.step = "w1"
                    st.rerun()

    # ── STEP w1: 종목·거리 편집 + 주관적 기록 ────────────────
    elif step == "w1":
        st.markdown('<div class="step-pill">✍️ 2단계 — 확인 & 오늘의 기분</div>',
                    unsafe_allow_html=True)
        chosen = st.session_state.wk_selected_list
        st.caption("종목명이나 거리가 이상하면 여기서 바로 고칠 수 있어요. "
                   "(트레드밀이면 GPS 거리가 틀리니 직접 입력을 권장합니다)")
        st.write("")

        for i, w in enumerate(chosen):
            st.markdown(f'<div class="section-label">운동 {i+1} · {w.get("local_time","")}</div>',
                        unsafe_allow_html=True)
            c1, c2 = st.columns([1, 1])
            with c1:
                st.text_input("종목명", value=w.get("sport", "운동"), key=f"sport_{i}")
            with c2:
                has_gps = bool(w.get("distance_m"))
                opts = ["자동(GPS)", "트레드밀·실내 (직접 입력)", "거리 없음"]
                # 이전에 편집하고 돌아온 경우 그때의 선택을 복원
                prev_src = w.get("distance_source")
                if prev_src == "manual":
                    default = 1
                elif prev_src == "none":
                    default = 2
                elif prev_src == "gps":
                    default = 0
                else:
                    default = 0 if has_gps else 2
                mode = st.radio("거리 처리", opts, index=default, key=f"distmode_{i}",
                                horizontal=False)
                if mode == opts[0] and has_gps:
                    st.caption(f"GPS 거리: {round(w['distance_m']/1000, 2)} km")
                elif mode == opts[1]:
                    prev_km = w.get("distance_km") or round((w.get("distance_m") or 0) / 1000, 2)
                    st.number_input("거리 직접 입력 (km)", min_value=0.0, step=0.1,
                                    value=float(prev_km), key=f"distkm_{i}")
            # 요약 미리보기
            preview = []
            if w.get("strain") is not None:
                preview.append(f"Strain {w['strain']}")
            if w.get("max_hr"):
                preview.append(f"최대 {w['max_hr']}bpm")
            if w.get("kcal"):
                preview.append(f"{w['kcal']}kcal")
            if preview:
                st.caption(" · ".join(preview))
            st.write("")

        st.divider()
        st.markdown("**오늘의 기분·몸 상태** (비워도 됩니다. 적으면 훨씬 생생한 일지가 됩니다)")
        # 3단계에 갔다가 돌아와도 이전에 쓴 내용이 유지되도록 저장값을 기본값으로
        before = st.text_area("운동 전 기분/컨디션", key="wk_before_in",
                              value=st.session_state.get("wk_before", ""),
                              placeholder="예: 아침부터 몸이 무거웠는데 그래도 나가보자 싶었다")
        body = st.text_area("운동 중·후 몸 상태", key="wk_body_in",
                            value=st.session_state.get("wk_body", ""),
                            placeholder="예: 초반엔 뻑뻑했는데 30분 지나니 리듬이 붙었다. 오른쪽 무릎 살짝 뻐근")
        after = st.text_area("운동 후 기분", key="wk_after_in",
                             value=st.session_state.get("wk_after", ""),
                             placeholder="예: 땀 흘리고 나니 머리가 맑아지고 개운했다")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("← 운동 다시 선택"):
                st.session_state.step = "w0"
                st.rerun()
        with col2:
            if st.button("분석하고 초안 만들기 →", type="primary"):
                finalized = []
                opts = ["자동(GPS)", "트레드밀·실내 (직접 입력)", "거리 없음"]
                for i, w in enumerate(chosen):
                    e = dict(w)
                    e["sport"] = st.session_state.get(f"sport_{i}", w.get("sport")).strip() or "운동"
                    mode = st.session_state.get(f"distmode_{i}", opts[2])
                    if mode == opts[0]:
                        e["distance_source"] = "gps"
                        e["distance_km"] = round((w.get("distance_m") or 0) / 1000, 2) or None
                    elif mode == opts[1]:
                        e["distance_source"] = "manual"
                        e["distance_km"] = st.session_state.get(f"distkm_{i}") or None
                    else:
                        e["distance_source"] = "none"
                        e["distance_km"] = None
                    finalized.append(e)
                st.session_state.wk_selected_list = finalized
                st.session_state.wk_before = before
                st.session_state.wk_body = body
                st.session_state.wk_after = after
                st.session_state.wk_summary = workout_agent.format_summary(
                    finalized, st.session_state.wk_recovery)
                # 최근 2주 추세는 숫자 요약이라 LLM 비용이 거의 들지 않는다
                if not st.session_state.get("wk_trend"):
                    st.session_state.wk_trend = whoop_agent.get_trend_summary()
                st.session_state.wk_analysis = ""
                st.session_state.wk_blog = ""
                st.session_state.wk_blog_prev = ""
                st.session_state.step = "w2"
                st.rerun()

    # ── STEP w2: 분석 + 일지 초안 ────────────────────────────
    elif step == "w2":
        st.markdown('<div class="step-pill">🧠 3단계 — 분석 & 운동 일지</div>',
                    unsafe_allow_html=True)
        prof = _profile()

        st.markdown('<div class="section-label">오늘의 운동 데이터</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="content-box">{st.session_state.wk_summary}</div>',
                    unsafe_allow_html=True)
        zone_bars = "".join(_zone_bar_html(w) for w in st.session_state.wk_selected_list)
        if zone_bars:
            st.markdown(zone_bars, unsafe_allow_html=True)
        st.write("")

        if not st.session_state.wk_analysis:
            with st.spinner("코치가 최근 추세와 함께 오늘 운동을 분석하는 중..."):
                st.session_state.wk_analysis = workout_agent.analyze_workout(
                    st.session_state.wk_summary, prof,
                    trend=st.session_state.get("wk_trend", ""))
            st.rerun()

        if not st.session_state.wk_blog:
            with st.spinner("운동 일지를 작성하는 중..."):
                st.session_state.wk_blog = workout_agent.write_workout_blog(
                    st.session_state.wk_summary, st.session_state.wk_analysis,
                    st.session_state.wk_before, st.session_state.wk_body,
                    st.session_state.wk_after, prof,
                    n_workouts=len(st.session_state.wk_selected_list))
            st.rerun()

        st.markdown('<div class="section-label">코치의 분석</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="content-box">{st.session_state.wk_analysis}</div>',
                    unsafe_allow_html=True)
        st.write("")
        st.markdown('<div class="section-label">운동 일지 초안</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="content-box">{st.session_state.wk_blog}</div>',
                    unsafe_allow_html=True)
        st.write("")

        st.caption("💡 종목명·거리 같은 '데이터'를 고치려면 아래 **← 데이터 다시 편집**으로 돌아가세요. "
                   "여기 수정 요청은 '글의 문장'을 다듬는 용도예요.")
        feedback = st.text_input("수정 요청 (없으면 비워두고 완성)", key="wk_fb",
            placeholder="예: 더 담백하게, 코치 조언을 짧게, 마무리를 다르게...")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✏️ 수정 요청", disabled=not feedback.strip(),
                         use_container_width=True):
                with st.spinner("수정 중..."):
                    sports = ", ".join(w.get("sport", "") for w in st.session_state.wk_selected_list)
                    st.session_state.wk_blog_prev = st.session_state.wk_blog  # 되돌리기용 백업
                    st.session_state.wk_blog = writer.revise_with_feedback(
                        "운동 일지", st.session_state.wk_blog, feedback, f"운동: {sports}")
                st.rerun()
        with col2:
            if st.session_state.get("wk_blog_prev"):
                if st.button("↩️ 수정 전으로 되돌리기", use_container_width=True):
                    st.session_state.wk_blog = st.session_state.wk_blog_prev
                    st.session_state.wk_blog_prev = ""
                    st.rerun()

        st.write("")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if st.button("← 데이터 다시 편집", use_container_width=True):
                st.session_state.step = "w1"
                st.rerun()
        with col_b:
            if st.button("✅ 완성 & 저장", type="primary", use_container_width=True):
                _save_and_show()
        with col_c:
            if st.button("↩️ 처음부터", use_container_width=True):
                _reset()

        if st.session_state.get("wk_saved_html"):
            _show_output()


def _summary_lines():
    """제목 아래 들어갈 운동 요약 줄 목록 (붙여넣기·Notion 공용)."""
    chosen = st.session_state.wk_selected_list
    rec = st.session_state.wk_recovery
    lines = []
    if len(chosen) > 1:
        for w in chosen:
            lines.append(workout_agent.workout_line(w))
            zl = workout_agent.zone_line(w)
            if zl:
                lines.append(f"   🫀 {zl}")
        if rec.get("recovery") is not None:
            lines.append(f"📊 전일 회복도 {rec['recovery']}%")
    else:
        rows = workout_agent.stat_rows(chosen, rec)
        stat_line = " · ".join(f"{label} {value}" for label, value in rows)
        if stat_line:
            lines.append(f"📊 {stat_line}")
        zl = workout_agent.zone_line(chosen[0]) if chosen else ""
        if zl:
            lines.append(f"🫀 {zl}")
    return lines


def _title():
    chosen = st.session_state.wk_selected_list
    sports = " + ".join(dict.fromkeys(w.get("sport", "운동") for w in chosen))
    date = chosen[0].get("local_time", "")[:5] if chosen else ""
    return f"오늘의 운동 — {sports}" + (f" ({date})" if date else "")


def _plain_text():
    """네이버에 그대로 붙여넣을 깔끔한 텍스트 (제목 + 운동 요약 + 본문 + 코치)."""
    lines = [_title(), ""]
    lines += _summary_lines()
    lines += ["", "─────────────", "", st.session_state.wk_blog.strip()]
    coach = (st.session_state.get("wk_analysis") or "").strip()
    if coach:
        lines += ["", "─────────────", "", "🧑‍🏫 코치의 한마디", "", coach]
    return "\n".join(lines)


def _save_and_show():
    chosen = st.session_state.wk_selected_list
    rec = st.session_state.wk_recovery
    sports = " + ".join(dict.fromkeys(w.get("sport", "운동") for w in chosen))
    total_min = sum(w.get("duration_min") or 0 for w in chosen)
    naver_html = build_naver_html(
        title=f"오늘의 운동 — {sports}",
        subtitle=f"총 {total_min}분 · {len(chosen)}개 세션" if len(chosen) > 1
                 else f"{total_min}분",
        stat_rows=workout_agent.stat_rows(chosen, rec),
        body_text=st.session_state.wk_blog,
        footer_box=("🧑‍🏫 코치의 한마디",
                    (st.session_state.get("wk_analysis") or "").strip()),
    )
    base = os.path.dirname(__file__)
    with open(os.path.join(base, "workout_log.txt"), "w", encoding="utf-8") as f:
        f.write(_plain_text())
    st.session_state.wk_saved_html = naver_html
    st.success("💾 저장 완료!")


def _show_output():
    plain = _plain_text()
    naver_html = st.session_state.wk_saved_html
    tab1, tab2, tab3 = st.tabs(
        ["📋 네이버에 붙여넣기 (추천)", "📥 다운로드", "🟢 HTML (표 포함·고급)"])
    with tab1:
        st.caption("아래 상자 오른쪽 위 복사 아이콘을 누르고, 네이버 글쓰기 화면에 그대로 붙여넣으세요. "
                   "서식 없이 깔끔하게 들어갑니다. (사진은 네이버에서 직접 추가)")
        st.code(plain, language=None)
    with tab2:
        st.download_button("📥 텍스트 파일 다운로드", data=plain,
            file_name="workout_log.txt", mime="text/plain")
        st.download_button("📥 HTML 파일 다운로드", data=wrap_document(naver_html, "오늘의 운동"),
            file_name="workout_log_naver.html", mime="text/html")
    with tab3:
        st.caption("네이버 새 에디터는 HTML 직접 붙여넣기를 지원하지 않습니다. "
                   "표까지 살리고 싶으면: 위 다운로드 탭에서 HTML 파일을 받아→브라우저로 열기→"
                   "화면을 전체 선택·복사→네이버에 붙여넣으면 서식이 어느 정도 유지됩니다.")
        st.code(naver_html, language="html")

    # ── Notion 자동 발행 ──────────────────────────────────
    st.write("")
    st.markdown('<div class="section-label">📝 Notion에 바로 올리기</div>',
                unsafe_allow_html=True)
    if not notion_agent.has_credentials():
        st.caption("Notion에 자동 발행하려면 NOTION_TOKEN / NOTION_PARENT_ID 를 설정하세요. "
                   "(설정법은 DEPLOY.md의 Notion 섹션 참고)")
    elif st.session_state.get("wk_notion_url"):
        st.success("✅ Notion에 발행됨!")
        st.link_button("🔗 Notion에서 열기", st.session_state.wk_notion_url)
    else:
        photos = st.file_uploader("📷 함께 올릴 운동 사진 (선택 · 여러 장 가능)",
                                  accept_multiple_files=True,
                                  type=["png", "jpg", "jpeg", "gif", "webp"],
                                  key="wk_photos")
        if st.button("📝 Notion에 올리기", type="primary"):
            with st.spinner("Notion에 글을 만드는 중..."):
                try:
                    image_ids = []
                    for f in (photos or []):
                        try:
                            image_ids.append(notion_agent.upload_image(
                                f.getvalue(), f.name, f.type))
                        except Exception as e:
                            st.warning(f"사진 업로드 실패: {f.name} — {e}")
                    first_sport = (st.session_state.wk_selected_list or [{}])[0].get("sport", "")
                    url = notion_agent.publish(
                        _title(), _summary_lines(), st.session_state.wk_blog,
                        coach_text=st.session_state.get("wk_analysis", ""),
                        image_ids=image_ids,
                        icon=workout_agent.sport_emoji(first_sport))
                    st.session_state.wk_notion_url = url
                    st.rerun()
                except Exception as e:
                    st.error(f"Notion 발행 실패: {e}")


def _reset():
    for k in ("wk_workouts", "wk_recovery", "wk_selected_list", "wk_summary",
              "wk_before", "wk_body", "wk_after", "wk_analysis", "wk_blog",
              "wk_saved_html", "wk_notion_url", "wk_blog_prev", "wk_trend"):
        st.session_state.pop(k, None)
    # 체크박스 상태도 정리
    for k in [k for k in list(st.session_state.keys()) if k.startswith("pick_wk_")]:
        st.session_state.pop(k, None)
    st.session_state.mode = None
    st.session_state.step = 0
    st.rerun()
