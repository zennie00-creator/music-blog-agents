"""📈 투자 일지 파이프라인.

시장 데이터 수집 → Grok 시장·테크 분석 → Claude 일지 작성 → Notion 발행.
기존 make.com(구글시트 → Perplexity → Gemini → Slack) 워크플로우를 대체한다.
"""
import os
from datetime import date as _date

from core import config
from core.notion import publish_page
from modes.investment import market_data
from modes.investment.analysis_agent import analyze_market
from modes.investment.journal_agent import write_journal

JOURNAL_DIR = os.path.join(config.ROOT_DIR, "journals")


def run(memo: str = "", publish: bool = True, save_local: bool = True) -> dict:
    """일지 파이프라인 실행. 결과(마크다운, notion URL, 로컬 경로)를 dict로 반환."""
    today = _date.today().isoformat()

    print(f"\n📊 [1/4] 시장 데이터 수집 중... ({today})")
    data_md = market_data.collect()
    print(data_md)

    print("\n🔍 [2/4] Grok - 시장·테크 분석 중...")
    analysis = analyze_market(today, data_md)
    print(analysis[:500] + ("..." if len(analysis) > 500 else ""))

    print("\n✍️ [3/4] Claude - 투자 일지 작성 중...")
    thesis = ""
    thesis_path = os.path.join(config.ROOT_DIR, "thesis.md")
    if os.path.exists(thesis_path):
        with open(thesis_path, encoding="utf-8") as f:
            thesis = f.read()
        print("  📌 thesis.md 반영 (나의 투자 전제)")
    journal = write_journal(today, data_md, analysis, memo, thesis=thesis)

    result = {"date": today, "journal": journal, "notion_url": "", "local_path": ""}

    if save_local:
        os.makedirs(JOURNAL_DIR, exist_ok=True)
        path = os.path.join(JOURNAL_DIR, f"{today}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(journal + "\n")
        result["local_path"] = path
        print(f"💾 로컬 저장: {path}")

    if publish:
        print("\n📤 [4/4] Notion 발행 중...")
        url = publish_page(f"📈 투자 일지 — {today}", journal)
        result["notion_url"] = url
        print(f"✅ 발행 완료: {url}")
    else:
        print("\n⏭️ [4/4] Notion 발행 건너뜀 (--no-publish)")

    return result
