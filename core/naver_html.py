"""네이버 블로그에 바로 붙여넣을 수 있는 HTML 생성 (음악·운동 공용).

네이버는 글 등록 공식 API가 없으므로, 완성된 HTML을 만들어
사용자가 '글쓰기 → HTML 편집기'에 붙여넣는 반자동 방식을 쓴다.
"""


def wrap_document(fragment, title="블로그 글"):
    """조각 HTML을 브라우저에서 바로 열 수 있는 완전한 문서로 감싼다.

    <meta charset="utf-8"> 를 넣어 한글이 깨지지 않게 한다.
    """
    return (
        '<!doctype html>\n<html lang="ko">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title}</title>\n</head>\n<body>\n{fragment}\n</body>\n</html>'
    )


def _img_table(images):
    """(url, label) 목록을 가로로 나열한 이미지 테이블."""
    cells = ""
    for url, label in images or []:
        if not url:
            continue
        cells += (
            '<td style="padding:8px;text-align:center;">'
            f'<img src="{url}" width="240" style="border-radius:8px;"/><br/>'
            f'<span style="font-size:12px;color:#999;">{label}</span></td>'
        )
    if not cells:
        return ""
    return f'<table style="margin:0 auto 24px;border:none;"><tr>{cells}</tr></table>'


def _stat_table(rows):
    """(label, value) 목록을 카드형 통계 테이블로. 운동 데이터 표시에 사용."""
    cells = ""
    for label, value in rows or []:
        if value in (None, ""):
            continue
        cells += (
            '<td style="padding:10px 16px;text-align:center;border:1px solid #e9e3d0;">'
            f'<div style="font-size:12px;color:#999;">{label}</div>'
            f'<div style="font-size:18px;font-weight:700;color:#2c2c2c;">{value}</div></td>'
        )
    if not cells:
        return ""
    return (
        '<table style="margin:0 auto 24px;border-collapse:collapse;">'
        f'<tr>{cells}</tr></table>'
    )


def build_naver_html(title, subtitle="", meta_lines=None, images=None,
                     stat_rows=None, body_text="", note="", footer_box=None,
                     extra_html=""):
    """네이버 블로그용 HTML 문자열을 만든다.

    title      : 큰 제목
    subtitle   : 제목 아래 회색 한 줄 (선택)
    meta_lines : 회색 메타 정보 줄 목록 (예: 앨범명) (선택)
    images     : (url, label) 목록 (선택)
    stat_rows  : (label, value) 통계 카드 목록 (선택, 운동용)
    body_text  : 본문. 빈 줄(\\n\\n) 기준으로 문단 분리
    note       : 본문 위 작은 회색 괄호 노트 (선택)
    footer_box : (제목, 텍스트) — 본문 아래 구분된 박스 영역 (선택, 코치 한마디 등)
    extra_html : 통계 카드와 본문 사이에 넣을 조각 HTML (선택, 심박존 표 등)
    """
    subtitle_html = (
        f'<p style="color:#888;font-size:14px;margin:0 0 8px;">{subtitle}</p>'
        if subtitle else ""
    )
    meta_html = "".join(
        f'<p style="color:#888;font-size:13px;margin:0 0 4px;">{line}</p>'
        for line in (meta_lines or []) if line
    )
    note_html = (
        f'<p style="color:#888;font-size:13px;margin:0 0 20px;">({note})</p>'
        if note else ""
    )
    paragraphs = "".join(
        f'<p style="margin:0 0 1.4em;line-height:1.9;">{p.strip()}</p>'
        for p in (body_text or "").strip().split("\n\n") if p.strip()
    )

    footer_html = ""
    if footer_box and footer_box[1]:
        f_title, f_text = footer_box
        f_paras = "".join(
            f'<p style="margin:0 0 1.2em;line-height:1.8;">{p.strip()}</p>'
            for p in f_text.strip().split("\n\n") if p.strip()
        )
        footer_html = f"""
<div style="margin-top:32px;background:#f6f8f4;border:1px solid #dde5d8;border-radius:10px;padding:20px 22px;">
<p style="font-size:15px;font-weight:700;margin:0 0 12px;color:#3d5a3d;">{f_title}</p>
{f_paras}
</div>"""

    return f"""<div style="max-width:680px;margin:0 auto;font-family:'나눔명조','Nanum Myeongjo',Georgia,serif;font-size:16px;color:#2c2c2c;">
{_img_table(images)}
<h2 style="font-size:20px;font-weight:700;margin:0 0 6px;">{title}</h2>
{subtitle_html}{meta_html}{note_html}
{_stat_table(stat_rows)}{extra_html}
<hr style="border:none;border-top:1px solid #e9e3d0;margin:20px 0;"/>
{paragraphs}{footer_html}
</div>"""
