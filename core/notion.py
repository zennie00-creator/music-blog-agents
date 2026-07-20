"""공통 Notion 발행 모듈 — 마크다운을 Notion 블록으로 변환해 데이터베이스에 페이지 생성."""
import requests

from core import config

_API = "https://api.notion.com/v1"


def _headers():
    if not config.NOTION_API_KEY:
        raise RuntimeError("NOTION_API_KEY가 설정되지 않았습니다 (.env 확인)")
    return {
        "Authorization": f"Bearer {config.NOTION_API_KEY}",
        "Notion-Version": config.NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _rich_text(text: str):
    # Notion rich_text 한 조각은 2000자 제한 → 분할
    return [{"type": "text", "text": {"content": text[i:i + 2000]}}
            for i in range(0, len(text), 2000)] or [{"type": "text", "text": {"content": ""}}]


def markdown_to_blocks(md: str):
    """단순 마크다운(제목/불릿/인용/구분선/문단)을 Notion 블록 리스트로 변환."""
    blocks = []
    for raw in md.split("\n"):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            blocks.append({"type": "heading_3", "heading_3": {"rich_text": _rich_text(stripped[4:])}})
        elif stripped.startswith("## "):
            blocks.append({"type": "heading_2", "heading_2": {"rich_text": _rich_text(stripped[3:])}})
        elif stripped.startswith("# "):
            blocks.append({"type": "heading_1", "heading_1": {"rich_text": _rich_text(stripped[2:])}})
        elif stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append({"type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": _rich_text(stripped[2:])}})
        elif stripped.startswith("> "):
            blocks.append({"type": "quote", "quote": {"rich_text": _rich_text(stripped[2:])}})
        elif stripped in ("---", "***", "___"):
            blocks.append({"type": "divider", "divider": {}})
        elif stripped.startswith("![") and "](" in stripped and stripped.endswith(")"):
            url = stripped[stripped.index("](") + 2:-1]
            # Notion external image URL은 과도하게 길면 400으로 거부된다.
            # QuickChart URL이 2000자를 넘는 경우가 있어 안전하게 링크 문단으로 대체.
            if len(url) <= 1900:
                blocks.append({"type": "image",
                               "image": {"type": "external", "external": {"url": url}}})
            else:
                label = stripped[2:stripped.index("](")] or "차트"
                blocks.append({"type": "paragraph", "paragraph": {"rich_text": [
                    {"type": "text", "text": {"content": f"{label}: ", }},
                    {"type": "text", "text": {"content": "차트 보기", "link": {"url": url}}},
                ]}})
        else:
            blocks.append({"type": "paragraph", "paragraph": {"rich_text": _rich_text(stripped)}})
    return blocks


def _title_property_name(database_id: str) -> str:
    """데이터베이스의 title 속성 이름을 조회 (DB마다 '이름'/'Name' 등 제각각)."""
    r = requests.get(f"{_API}/databases/{database_id}", headers=_headers(), timeout=30)
    r.raise_for_status()
    for name, prop in r.json().get("properties", {}).items():
        if prop.get("type") == "title":
            return name
    return "Name"


def publish_page(title: str, markdown_body: str, database_id: str = "") -> str:
    """마크다운 본문을 Notion 데이터베이스에 새 페이지로 발행하고 URL을 반환."""
    database_id = database_id or config.NOTION_DATABASE_ID
    if not database_id:
        raise RuntimeError("NOTION_DATABASE_ID가 설정되지 않았습니다 (.env 확인)")

    blocks = markdown_to_blocks(markdown_body)
    title_prop = _title_property_name(database_id)

    payload = {
        "parent": {"database_id": database_id},
        "properties": {title_prop: {"title": _rich_text(title)}},
        "children": blocks[:100],  # 페이지 생성 시 children은 100블록 제한
    }
    r = requests.post(f"{_API}/pages", headers=_headers(), json=payload, timeout=60)
    r.raise_for_status()
    page = r.json()
    page_id = page["id"]

    # 100블록 초과분은 append API로 나눠서 추가
    rest = blocks[100:]
    for i in range(0, len(rest), 100):
        r = requests.patch(
            f"{_API}/blocks/{page_id}/children",
            headers=_headers(),
            json={"children": rest[i:i + 100]},
            timeout=60,
        )
        r.raise_for_status()

    return page.get("url", "")
