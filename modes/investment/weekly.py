"""주간 회고 — 트레이딩 저널의 핵심은 기록이 아니라 회고 주기다.

지난 7일의 일지·브리핑 + 신호 로그 + 투자 전제를 모아 Claude가 회고를 쓴다:
- 내 판단 vs 실제 시장 결과 (적중/빗나감을 솔직하게)
- 전제 상태의 주간 변화 (기둥별로 흔들린 게 있었는지)
- 신호 성적표 요약
- 다음 주 체크포인트

사용: python invest.py --weekly  (Actions: 토요일 아침 자동)
"""
import glob
import os
import re
from datetime import date, timedelta

from core import config
from core.llm import ask_claude
from core.notion import publish_page
from modes.investment import market_data, signal_log
from modes.investment.pipeline import JOURNAL_DIR, load_thesis, _save_local

MAX_DOC_CHARS = 4000   # 일지 1건당 프롬프트에 넣는 최대 길이
LOOKBACK_DAYS = 7

SYSTEM_PROMPT = """당신은 개인 투자자의 주간 회고를 정리하는 에디터입니다.
지난 한 주의 일지들과 신호 기록을 검토해 '판단과 결과의 갭'을 드러내는 것이
목적입니다. 원칙:
- 적중한 판단과 빗나간 판단을 똑같이 솔직하게 다루세요. 아부 금지.
- 빗나간 판단은 원인을 구분하세요: 전제가 틀렸나 / 신호를 무시했나 /
  타이밍 문제였나 / 그냥 운이었나.
- 반복되는 패턴(예: 신호가 떠도 행동하지 않음)이 보이면 지적하세요.
- 담백한 한국어. 결과물은 마크다운만 출력."""

USER_TEMPLATE = """이번 주 회고를 작성해 주세요. 오늘: {today}
{thesis_block}
[지난 7일의 일지·브리핑] (오래된 것부터)
{docs}

[신호 성적표]
{signal_report}

형식:
# 🗓 주간 회고 — {today}

## 이번 주 시장 한 줄 요약

## 판단 vs 결과
(이번 주 일지에 적었던 판단·계획들이 실제로 어떻게 됐는지. 적중/빗나감 구분,
 빗나간 것은 원인 분류)

## 전제 점검
(기둥별로 이번 주에 흔들린 근거가 있었는지. 없으면 '유효 유지' 한 줄)

## 신호 돌아보기
(이번 주 떴던 신호들과 그 후 실제 움직임. 성적표 데이터가 부족하면 부족하다고)

## 다음 주 체크포인트
(이벤트·지표·감시 레벨 불릿 3~5개)"""


def _strip_charts(text: str) -> str:
    # "## 차트"는 헤딩만 남고 이미지는 Notion 파일 블록으로 붙으므로(본문엔 없음)
    # 헤딩 이후 어떤 형태든(줄바꿈+구 QuickChart 링크 포함) 잘라낸다.
    return re.split(r"\n## 차트\b", text)[0]


def collect_week_docs(today: date):
    """지난 LOOKBACK_DAYS일의 일지/브리핑 파일을 날짜순으로 모은다."""
    docs = []
    if not os.path.isdir(JOURNAL_DIR):
        return docs
    cutoff = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    for path in sorted(glob.glob(os.path.join(JOURNAL_DIR, "*.md"))):
        name = os.path.basename(path)
        m = re.match(r"(\d{4}-\d{2}-\d{2})(-brief)?\.md$", name)
        if not m or m.group(1) < cutoff:
            continue
        with open(path, encoding="utf-8") as f:
            body = _strip_charts(f.read())[:MAX_DOC_CHARS]
        docs.append((name, body))
    return docs


def run_weekly(publish: bool = True, save_local: bool = True) -> dict:
    today = date.today()
    thesis = load_thesis()

    print(f"\n🗓 주간 회고 생성 ({today.isoformat()})")
    docs = collect_week_docs(today)
    if not docs:
        print("⚠️ 지난 7일의 일지가 없습니다 — 일지가 쌓인 뒤 실행하세요.")
        return {"date": today.isoformat(), "review": "", "notion_url": ""}
    print(f"  📚 일지 {len(docs)}건 수집")

    print("  📊 시세 수집 중 (신호 성적표 계산)...")
    ctx = market_data.collect_context()
    signal_report = signal_log.performance_report(ctx)

    thesis_block = f"\n[나의 투자 전제]\n{thesis.strip()}\n" if thesis.strip() else ""
    docs_text = "\n\n---\n\n".join(f"### {name}\n{body}" for name, body in docs)

    print("  ✍️ Claude - 회고 작성 중...")
    review = ask_claude(
        SYSTEM_PROMPT,
        USER_TEMPLATE.format(today=today.isoformat(), thesis_block=thesis_block,
                             docs=docs_text, signal_report=signal_report),
    )
    # 성적표 원본도 회고 뒤에 붙여 보존
    review += "\n\n---\n\n" + signal_report

    result = {"date": today.isoformat(), "review": review, "notion_url": "", "local_path": ""}
    if save_local:
        result["local_path"] = _save_local(f"weekly-{today.isoformat()}.md", review)
        print(f"  💾 로컬 저장: {result['local_path']}")
    if publish:
        url = publish_page(f"🗓 주간 회고 — {today.isoformat()}", review)
        result["notion_url"] = url
        print(f"  ✅ Notion 발행: {url}")
    return result
