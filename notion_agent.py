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


def _quote(text):
    return {"object": "block", "type": "quote",
            "quote": {"rich_text": _rich(text)}}


def _bullet(text):
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": _rich(text)}}


def image_upload_block(file_upload_id):
    """업로드한 파일을 이미지 블록으로."""
    return {"object": "block", "type": "image",
            "image": {"type": "file_upload",
                      "file_upload": {"id": file_upload_id}}}


def upload_image(data, filename, mime=None):
    """이미지 파일을 Notion에 업로드하고 file_upload id를 반환한다. (20MB 이하)"""
    r = requests.post(f"{API}/file_uploads", headers=_headers(),
                      json={"mode": "single_part", "filename": filename},
                      timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"업로드 준비 실패 {r.status_code}: {r.text[:200]}")
    fid = r.json()["id"]
    h = {"Authorization": f"Bearer {os.environ.get('NOTION_TOKEN','')}",
         "Notion-Version": VERSION}
    r2 = requests.post(f"{API}/file_uploads/{fid}/send", headers=h,
                       files={"file": (filename, data, mime or "image/png")},
                       timeout=60)
    if r2.status_code >= 300:
        raise RuntimeError(f"업로드 실패 {r2.status_code}: {r2.text[:200]}")
    return fid


def md_blocks(md_text):
    """간단한 마크다운(#, ##, ###, -, >, ---)을 Notion 블록으로 변환."""
    blocks = []
    for raw in (md_text or "").splitlines():
        s = raw.strip().replace("**", "")
        if not s:
            continue
        if s.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                           "heading_3": {"rich_text": _rich(s[4:])}})
        elif s.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": _rich(s[3:])}})
        elif s.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1",
                           "heading_1": {"rich_text": _rich(s[2:])}})
        elif s in ("---", "___", "***"):
            blocks.append(_divider())
        elif s.startswith(("- ", "* ")):
            blocks.append(_bullet(s[2:]))
        elif s.startswith("> "):
            blocks.append(_quote(s[2:]))
        else:
            blocks.append(_paragraph(s))
    return blocks


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


def create_page(title, children, parent_id=None, icon=None):
    """Notion에 페이지를 만들고 URL을 반환한다.

    parent_id : 지정하면 그 페이지/DB 아래에, 없으면 NOTION_PARENT_ID 사용
    icon      : 이모지 아이콘 (예: '🏃')
    children  : 블록 목록 (100개 초과 시 나눠서 추가)
    """
    if requests is None:
        raise RuntimeError("requests 모듈이 필요합니다.")
    pid = (parent_id or _parent_id()).strip()
    kind, title_prop = _resolve_parent(pid)

    first, rest = children[:90], children[90:]
    if kind == "database":
        payload = {
            "parent": {"database_id": pid},
            "properties": {title_prop: {"title": _rich(title)}},
            "children": first,
        }
    else:
        payload = {
            "parent": {"page_id": pid},
            "properties": {"title": {"title": _rich(title)}},
            "children": first,
        }
    if icon:
        payload["icon"] = {"type": "emoji", "emoji": icon}

    r = requests.post(f"{API}/pages", headers=_headers(), json=payload, timeout=30)
    if r.status_code >= 300 and icon:
        # 일부 이모지는 아이콘으로 거부될 수 있어 아이콘 없이 재시도
        payload.pop("icon", None)
        r = requests.post(f"{API}/pages", headers=_headers(), json=payload, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"Notion API 오류 {r.status_code}: {r.text[:300]}")
    res = r.json()

    # 100블록 제한: 나머지는 이어서 추가
    page_id = res.get("id")
    while rest and page_id:
        chunk, rest = rest[:90], rest[90:]
        r2 = requests.patch(f"{API}/blocks/{page_id}/children",
                            headers=_headers(), json={"children": chunk}, timeout=30)
        if r2.status_code >= 300:
            break  # 페이지는 이미 생성됨 — 남은 블록만 실패
    return res.get("url", "")


def publish(title, summary_lines, body_text, coach_text="",
            image_ids=None, icon=None, parent_id=None):
    """운동/음악 일지 형식으로 Notion 글을 생성하고 URL을 반환한다.

    coach_text : 코치 분석 원문 — 본문 아래 별도 영역(제목+인용)
    image_ids  : upload_image로 올린 파일 id 목록 — 요약 아래 이미지로 삽입
    """
    children = []
    if summary_lines:
        children.append(_callout("\n".join(summary_lines)))
    for fid in (image_ids or []):
        children.append(image_upload_block(fid))
    children += _body_blocks(body_text)

    if coach_text and coach_text.strip():
        children.append(_divider())
        children.append(_heading("🧑‍🏫 코치의 한마디"))
        for para in coach_text.strip().split("\n\n"):
            if para.strip():
                children.append(_quote(para.strip()))

    return create_page(title, children, parent_id=parent_id, icon=icon)
