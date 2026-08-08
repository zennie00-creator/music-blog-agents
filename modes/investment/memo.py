"""오늘의 메모 — Notion 페이지로 주고받는다.

일지의 중심은 메모인데, 메모를 넣는 경로가 GitHub Actions 입력칸뿐이라 폰에서
쓰기가 번거로웠다. Notion에 '오늘의 메모' 페이지를 미리 만들어 두면 폰 Notion 앱에서
한 줄 적어 두기만 하면 되고, 밤에 도는 일지 실행이 그걸 읽어 간다.

저녁 실행이 페이지를 만들고(=메모 쓸 시간 알림 역할), 밤 실행이 읽어 간다.
"""
from datetime import date as _date

from core import notion

PREFIX = "📝 오늘의 메모"

# 페이지를 열었을 때 뭘 써야 할지 보이게 하는 안내. 읽을 때는 걷어낸다.
TEMPLATE = """> 오늘 하루의 매매·판단·느낌을 아래에 자유롭게 적어 두세요.
> 밤 일지 실행이 이 페이지를 읽어 '나의 생각'으로 씁니다. 비워 두면 일지를 건너뜁니다.

"""

_GUIDE_MARK = ">"


def page_title(day: str = "") -> str:
    return f"{PREFIX} — {day or _date.today().isoformat()}"


def _find(day: str = ""):
    title = page_title(day)
    for p in notion.list_pages(title, limit=5):
        if p["title"].strip() == title:
            return p
    return None


def ensure(day: str = "") -> tuple:
    """오늘의 메모 페이지를 준비한다 → (url, 새로_만들었는지).

    이미 있으면 손대지 않는다 — 덮어쓰면 적어 둔 메모가 날아간다."""
    day = day or _date.today().isoformat()
    page = _find(day)
    if page:
        return page.get("url", ""), False
    return notion.publish_page(page_title(day), TEMPLATE), True


def load(day: str = "") -> str:
    """메모 페이지에서 사용자가 쓴 내용만 → 문자열. 없으면 빈 문자열.

    안내문(인용 블록)은 사용자가 쓴 게 아니므로 걷어낸다."""
    page = _find(day)
    if not page:
        return ""
    body = notion.read_page(page["id"])
    lines = [ln for ln in body.split("\n")
             if ln.strip() and not ln.lstrip().startswith(_GUIDE_MARK)]
    return "\n".join(lines).strip()
