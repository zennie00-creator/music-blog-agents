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
        # Claude가 헤딩을 굵게 감싸는 경우(**## 제목**)가 있어 헤딩 인식이 깨진다.
        # 줄 전체를 감싼 ** 를 벗겨 헤딩 마커가 앞에 오게 정규화한다.
        if stripped.startswith("**") and stripped.endswith("**") and \
                stripped[2:-2].lstrip().startswith("#"):
            stripped = stripped[2:-2].strip()
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


def _upload_png(png: bytes, filename: str) -> str:
    """PNG 바이트를 Notion에 업로드하고 file_upload id를 반환 (실패 시 "").

    2단계: (1) POST /file_uploads 로 업로드 슬롯 생성 → upload_url 획득,
    (2) 그 URL로 multipart 파일 전송. 외부 URL을 Notion이 가져가는 방식이 아니라
    파일을 직접 넣으므로 'image couldn't be loaded'가 원천 발생하지 않는다."""
    try:
        slot = _request("POST", f"{_API}/file_uploads",
                        {"filename": filename, "content_type": "image/png"})
        upload_url = slot.get("upload_url") or f"{_API}/file_uploads/{slot['id']}/send"
        # 전송 단계는 multipart — Content-Type 헤더는 requests가 boundary와 함께 설정
        headers = {"Authorization": f"Bearer {config.NOTION_API_KEY}",
                   "Notion-Version": config.NOTION_VERSION}
        r = requests.post(upload_url, headers=headers,
                          files={"file": (filename, png, "image/png")}, timeout=60)
        if not r.ok:
            print(f"  ⚠️ 차트 업로드 전송 실패: {r.status_code} {r.text[:200]}")
            return ""
        return slot["id"]
    except Exception as e:
        print(f"  ⚠️ 차트 업로드 실패 ({filename}): {e}")
        return ""


def _image_block(file_upload_id: str, caption: str = ""):
    img = {"type": "file_upload", "file_upload": {"id": file_upload_id}}
    if caption:
        img["caption"] = [{"type": "text", "text": {"content": caption[:2000]}}]
    return {"type": "image", "image": img}


def _append_chart_images(page_id: str, image_specs):
    """[(캡션, PNG바이트)] → 업로드 후 이미지 블록으로 append. 실패한 차트는 스킵."""
    if not image_specs:
        return
    blocks = []
    for i, (caption, png) in enumerate(image_specs):
        fid = _upload_png(png, f"chart_{i}.png")
        if fid:
            blocks.append(_image_block(fid, caption))
    if blocks:
        _append_blocks(page_id, blocks)


def _title_property_name(database_id: str) -> str:
    """데이터베이스의 title 속성 이름을 조회 (DB마다 '이름'/'Name' 등 제각각)."""
    r = requests.get(f"{_API}/databases/{database_id}", headers=_headers(), timeout=30)
    r.raise_for_status()
    for name, prop in r.json().get("properties", {}).items():
        if prop.get("type") == "title":
            return name
    return "Name"


def publish_page(title: str, markdown_body: str, database_id: str = "",
                 image_specs=None) -> str:
    """마크다운 본문을 Notion 데이터베이스에 새 페이지로 발행하고 URL을 반환.

    제목만으로 먼저 페이지를 만든 뒤 본문 블록을 append한다. 이렇게 하면
    본문 블록 하나가 잘못돼도(예: Notion이 거부하는 차트 이미지 URL) 페이지는
    반드시 생성되고, 문제 블록만 건너뛴다. (이전에는 400 하나로 전체 실패)

    image_specs=[(캡션, PNG바이트)]를 주면 본문 뒤에 차트를 '파일'로 업로드해
    이미지 블록으로 붙인다 — 외부 URL fetch 실패(quickchart 'couldn't be loaded')를
    피하는 경로. 업로드 실패한 차트는 조용히 건너뛰고 페이지는 정상 발행된다.
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

    # 3) 차트 PNG를 파일로 업로드해 이미지 블록으로 append
    _append_chart_images(page_id, image_specs)

    return page.get("url", "")
