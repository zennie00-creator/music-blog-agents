"""토론 기록의 저장소 — Notion.

왜 파일이 아니라 Notion인가:
- Streamlit Cloud는 파일시스템이 휘발성이라 세션이 끊기면 대화가 사라진다
  (실제로 라운드 중간에 검토 의견이 통째로 날아간 적이 있다).
- GitHub Actions는 매 실행이 새 컨테이너이고 discussions/는 .gitignore 대상이라
  일지 작성 단계에서 오늘의 토론을 절대 볼 수 없었다.
Notion에 두면 폰(Streamlit)에서 한 토론을 다음 날 아침 Actions가 그대로 읽는다.

저장 모델은 append-only다. 토론은 발언이 뒤에 붙기만 하고 앞이 바뀌지 않으므로,
Notion에 '본문 교체' API가 없다는 제약이 문제가 되지 않는다. 라운드마다 새로 생긴
발언만 덧붙이고, 이미 쓴 개수는 호출자가 커서로 들고 있는다.

페이지 형식 (파싱이 깨지지 않게 발언자 줄을 단독으로 둔다):
    **[나]**
    질문 내용...

    **[Grok]**
    답변...
"""
import re
from datetime import date as _date

from core import notion

PREFIX = "🗣️ 투자 토론"
_SPEAKER_RE = re.compile(r"^\*\*\[(.+?)\]\*\*$")

# 요약도 같은 마커 체계로 적어 둔다 — 별도 섹션을 두면 파싱 규칙이 하나 더 는다
SUMMARY_SPEAKER = "요약"


def page_title(day: str = "", topic: str = "") -> str:
    day = day or _date.today().isoformat()
    return f"{PREFIX} — {day}" + (f" · {topic.strip()}" if topic.strip() else "")


def _render(messages) -> str:
    """[(발언자, 내용)] → 페이지에 덧붙일 마크다운."""
    out = []
    for speaker, text in messages:
        out.append(f"**[{speaker}]**")
        out.append(str(text).strip())
    return "\n\n".join(out)


def parse(text: str):
    """페이지 본문 텍스트 → [(발언자, 내용)]. 마커가 없으면 빈 목록."""
    msgs, speaker, buf = [], None, []

    def flush():
        if speaker is not None:
            msgs.append((speaker, "\n".join(buf).strip()))

    for line in (text or "").split("\n"):
        m = _SPEAKER_RE.match(line.strip())
        if m:
            flush()
            speaker, buf = m.group(1), []
        elif speaker is not None:
            buf.append(line)
    flush()
    return [(s, t) for s, t in msgs if t]


def _find_page(title: str):
    """제목이 정확히 일치하는 페이지 → {id, url}. 없으면 None.

    list_pages는 '포함' 검색이라 '… — 2026-08-08'이 '… — 2026-08-08 · 주제'도
    잡는다. 접두사가 겹치는 다른 토론에 발언을 덧붙이지 않도록 정확히 비교한다."""
    for p in notion.list_pages(title, limit=10):
        if p["title"].strip() == title:
            return p
    return None


def append(messages, day: str = "", topic: str = "") -> str:
    """발언들을 오늘의 토론 페이지에 덧붙인다 (없으면 생성) → 페이지 URL.

    messages는 '아직 저장하지 않은 것'만 넘긴다. 빈 목록이면 아무것도 하지 않는다."""
    if not messages:
        return ""
    title = page_title(day, topic)
    body = _render(messages)
    page = _find_page(title)
    if page:
        notion.append_markdown(page["id"], body)
        return page.get("url", "")
    return notion.publish_page(title, body)


def save_summary(summary: str, day: str = "", topic: str = "") -> str:
    """마무리 요약을 같은 페이지에 덧붙인다."""
    if not summary.strip():
        return ""
    return append([(SUMMARY_SPEAKER, summary)], day, topic)


def load(day: str = "", topic: str = ""):
    """저장된 토론을 복원 → [(발언자, 내용)]. 없으면 빈 목록."""
    page = _find_page(page_title(day, topic))
    if not page:
        return []
    return parse(notion.read_page(page["id"]))


def load_day(day: str = ""):
    """그 날짜의 모든 토론 → [(주제, [(발언자, 내용)])].

    주제는 페이지 제목의 ' · ' 뒤에서 얻는다 (Streamlit 토론은 주제가 없어 빈 문자열)."""
    day = day or _date.today().isoformat()
    head = f"{PREFIX} — {day}"
    out = []
    for p in notion.list_pages(head, limit=10):
        title = p["title"].strip()
        if not title.startswith(head):
            continue
        topic = title[len(head):].lstrip(" ·").strip()
        msgs = parse(notion.read_page(p["id"]))
        if msgs:
            out.append((topic, msgs))
    return out
