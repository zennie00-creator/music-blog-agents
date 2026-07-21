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


def _request(method: str, url: str, payload):
    """Notion 요청. 실패 시 응답 본문(원인 설명)을 포함해 예외를 던진다.

    Notion의 4xx는 body의 message 필드에 정확한 원인이 담겨 있는데
    raise_for_status()는 이를 버려서 디버깅이 불가능하다.
    """
    r = requests.request(method, url, headers=_headers(), json=payload, timeout=60)
    if not r.ok:
        detail = r.text[:600].replace("\n", " ")
        raise RuntimeError(f"Notion {r.status_code} {method} {url.rsplit('/', 2)[-1]}: {detail}")
    return r.json()


def _append_blocks(page_id: str, blocks):
    """블록을 100개 배치로 append. 배치가 실패하면 절반씩 나눠 재시도해
    문제 블록(예: Notion이 거부하는 이미지 URL)만 건너뛰고 나머지는 살린다."""
    url = f"{_API}/blocks/{page_id}/children"

    def _append_batch(batch):
        if not batch:
            return
        try:
            _request("PATCH", url, {"children": batch})
        except RuntimeError as e:
            if len(batch) == 1:
                btype = batch[0].get("type", "?")
                print(f"  ⚠️ Notion 블록 1개 건너뜀 ({btype}): {e}")
                return
            mid = len(batch) // 2
            _append_batch(batch[:mid])  # 순서 유지: 왼쪽 먼저
            _append_batch(batch[mid:])

    for i in range(0, len(blocks), 100):
        _append_batch(blocks[i:i + 100])


def _title_property_name(database_id: str) -> str:
    """데이터베이스의 title 속성 이름을 조회 (DB마다 '이름'/'Name' 등 제각각)."""
    r = requests.get(f"{_API}/databases/{database_id}", headers=_headers(), timeout=30)
    r.raise_for_status()
    for name, prop in r.json().get("properties", {}).items():
        if prop.get("type") == "title":
            return name
    return "Name"


def publish_page(title: str, markdown_body: str, database_id: str = "") -> str:
    """마크다운 본문을 Notion 데이터베이스에 새 페이지로 발행하고 URL을 반환.

    제목만으로 먼저 페이지를 만든 뒤 본문 블록을 append한다. 이렇게 하면
    본문 블록 하나가 잘못돼도(예: Notion이 거부하는 차트 이미지 URL) 페이지는
    반드시 생성되고, 문제 블록만 건너뛴다. (이전에는 400 하나로 전체 실패)
    """
    database_id = database_id or config.NOTION_DATABASE_ID
    if not database_id:
        raise RuntimeError("NOTION_DATABASE_ID가 설정되지 않았습니다 (.env 확인)")

    blocks = markdown_to_blocks(markdown_body)
    title_prop = _title_property_name(database_id)

    # 1) 제목만으로 페이지 생성 — 본문 블록 문제와 분리 (실패하면 원인이 예외에 담김)
    page = _request("POST", f"{_API}/pages", {
        "parent": {"database_id": database_id},
        "properties": {title_prop: {"title": _rich_text(title)}},
    })
    page_id = page["id"]

    # 2) 본문 블록을 배치로 append (문제 블록은 자동 격리)
    _append_blocks(page_id, blocks)

    return page.get("url", "")
