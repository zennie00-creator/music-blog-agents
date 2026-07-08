"""Notion 자동 포스팅 — API로 글을 직접 생성한다.

네이버와 달리 Notion은 공식 API로 페이지 생성을 지원하므로,
복사·붙여넣기 없이 버튼 한 번으로 자동 발행할 수 있다.

필요한 환경변수:
  NOTION_TOKEN      Notion Integration의 Internal Integration Secret
  NOTION_PARENT_ID  글을 쌓을 부모의 ID (페이지 ID 또는 데이터베이스 ID 모두 지원)

부모가 페이지인지 데이터베이스인지는 자동으로 감지해서 맞춘다.
자격증명이 없으면 has_credentials()가 False를 반환해 버튼이 비활성화된다.
"""
import os

try:
    import requests
except ImportError:
    requests = None

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"


def has_credentials():
    return bool(os.environ.get("NOTION_TOKEN") and os.environ.get("NOTION_PARENT_ID"))


def _headers():
    return {
        "Authorization": f"Bearer {os.environ.get('NOTION_TOKEN','')}",
        "Notion-Version": VERSION,
        "Content-Type": "application/json",
    }


def _parent_id():
    # Notion ID는 하이픈이 있어도/없어도 동작한다
    return (os.environ.get("NOTION_PARENT_ID", "") or "").strip()


# ── 블록 빌더 ─────────────────────────────────────────────────────────
def _rich(text):
    return [{"type": "text", "text": {"content": text[:2000]}}]


def _heading(text):
    return {"object": "block", "type": "heading_3",
            "heading_3": {"rich_text": _rich(text)}}


def _paragraph(text):
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": _rich(text)}}


def _callout(text, emoji="📊"):
    return {"object": "block", "type": "callout",
            "callout": {"rich_text": _rich(text),
                        "icon": {"type": "emoji", "emoji": emoji}}}


def _divider():
    return {"object": "block", "type": "divider", "divider": {}}


# 운동 소제목에 쓰이는 이모지 (이걸로 시작하는 한 줄은 소제목으로 본다)
_HEADING_EMOJIS = "🏃🚶🚴🏊🏋️🧘🧗🎾⚽💪"


def _body_blocks(body_text):
    """본문 텍스트를 Notion 블록 목록으로. 이모지로 시작하는 한 줄은 소제목."""
    blocks = []
    for chunk in (body_text or "").strip().split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if set(chunk) <= set("─-—="):  # 구분선
            blocks.append(_divider())
        elif "\n" not in chunk and chunk[0] in _HEADING_EMOJIS and len(chunk) <= 30:
            blocks.append(_heading(chunk))
        else:
            blocks.append(_paragraph(chunk))
    return blocks


# ── 발행 ──────────────────────────────────────────────────────────────
def _resolve_parent(pid):
    """부모 ID가 페이지인지 DB인지 감지. (kind, title_property_name) 반환."""
    r = requests.get(f"{API}/pages/{pid}", headers=_headers(), timeout=20)
    if r.status_code == 200:
        return "page", None
    r = requests.get(f"{API}/databases/{pid}", headers=_headers(), timeout=20)
    if r.status_code == 200:
        props = r.json().get("properties", {})
        title_prop = next((name for name, p in props.items()
                           if p.get("type") == "title"), "Name")
        return "database", title_prop
    # 감지 실패 시 페이지로 가정
    return "page", None


def publish(title, summary_lines, body_text):
    """Notion에 글 한 편을 생성하고 URL을 반환한다."""
    if requests is None:
        raise RuntimeError("requests 모듈이 필요합니다.")
    pid = _parent_id()
    kind, title_prop = _resolve_parent(pid)

    children = []
    if summary_lines:
        children.append(_callout("\n".join(summary_lines)))
    children += _body_blocks(body_text)

    if kind == "database":
        payload = {
            "parent": {"database_id": pid},
            "properties": {title_prop: {"title": _rich(title)}},
            "children": children,
        }
    else:
        payload = {
            "parent": {"page_id": pid},
            "properties": {"title": {"title": _rich(title)}},
            "children": children,
        }

    r = requests.post(f"{API}/pages", headers=_headers(), json=payload, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"Notion API 오류 {r.status_code}: {r.text[:300]}")
    return r.json().get("url", "")
