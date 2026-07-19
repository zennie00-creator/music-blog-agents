"""📈 투자 파이프라인 — 하루 두 번의 리듬.

  아침 (미국 장 마감 후, ~06:30 KST) — run_brief():
    데이터·신호 수집 → Grok 분석 + 전제 상태 보드 → 📊 모닝 브리핑 발행.
    메모 없음, Claude 호출 없음 (대시보드+신호+Grok으로 충분 → 비용 절감).

  오후 (한국 장 마감 후) — run():
    아침 브리핑의 Grok 분석을 재사용하고, 한국 장 마감이 반영된 데이터만
    새로 수집 → 내 메모와 합쳐 Claude가 📈 투자 일지 작성 → 발행.
    아침 브리핑이 없으면(로컬 미실행 등) Grok 분석을 즉석에서 실행.

기존 make.com(구글시트 → Perplexity → Gemini → Slack) 워크플로우를 대체한다.
"""
import json
import os
from datetime import date as _date

from core import config
from core.notify import alert_lines, push
from core.notion import publish_page
from modes.investment import charts, market_data, signal_log, signals
from modes.investment.analysis_agent import analyze_market
from modes.investment.journal_agent import write_journal

JOURNAL_DIR = os.path.join(config.ROOT_DIR, "journals")


def load_trades(days: int = 14) -> str:
    """trades.md의 최근 N일 매매 기록 (plan vs action 점검용). 없으면 빈 문자열."""
    path = os.path.join(config.ROOT_DIR, "trades.md")
    if not os.path.exists(path):
        return ""
    from datetime import timedelta
    cutoff = (_date.today() - timedelta(days=days)).isoformat()
    lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            # "- 2026-07-18 ..." 형식의 최근 기록만
            if s.startswith("- 2") and len(s) > 12 and s[2:12] >= cutoff:
                lines.append(s)
    return "\n".join(lines)


def load_thesis() -> str:
    """리포 루트의 thesis.md (나의 투자 전제). 없으면 빈 문자열."""
    path = os.path.join(config.ROOT_DIR, "thesis.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


def _collect():
    ctx = market_data.collect_context()
    data_md = market_data.dashboard_md(ctx) + "\n\n" + signals.run_all(ctx)
    if signal_log.record(ctx):
        print("  🗂 신호 로그 기록 (signal_log/)")
    return ctx, data_md


def _brief_state_path(date: str) -> str:
    return os.path.join(JOURNAL_DIR, f".brief-{date}.json")


def _save_local(name: str, content: str) -> str:
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    path = os.path.join(JOURNAL_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content + "\n")
    return path


def load_brief(date: str):
    """아침 브리핑 상태(json). 없으면 None."""
    path = _brief_state_path(date)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def run_brief(publish: bool = True, save_local: bool = True) -> dict:
    """아침 모닝 브리핑 — 자동 실행용 (Claude 호출 없음)."""
    today = _date.today().isoformat()
    thesis = load_thesis()

    print(f"\n📊 [1/3] 시장 데이터 수집 중... ({today})")
    ctx, data_md = _collect()
    print(data_md)

    print("\n🔍 [2/3] Grok - 시장·테크 분석 중..." + (" (전제 상태 보드 포함)" if thesis else ""))
    analysis = analyze_market(today, data_md, thesis=thesis)
    print(analysis[:500] + ("..." if len(analysis) > 500 else ""))

    brief = f"# 📊 모닝 브리핑 — {today}\n\n{data_md}\n\n{analysis}"
    charts_md = charts.charts_markdown(ctx)
    if charts_md:
        brief += "\n\n## 차트\n" + charts_md

    result = {"date": today, "brief": brief, "notion_url": "", "local_path": ""}

    if save_local:
        result["local_path"] = _save_local(f"{today}-brief.md", brief)
        # 오후 일지가 재사용할 상태 저장 (Grok 분석 재실행 방지)
        with open(_brief_state_path(today), "w", encoding="utf-8") as f:
            json.dump({"date": today, "analysis": analysis}, f, ensure_ascii=False)
        print(f"💾 로컬 저장: {result['local_path']}")

    if publish:
        print("\n📤 [3/3] Notion 발행 중...")
        url = publish_page(f"📊 모닝 브리핑 — {today}", brief)
        result["notion_url"] = url
        print(f"✅ 발행 완료: {url}")
    else:
        print("\n⏭️ [3/3] Notion 발행 건너뜀 (--no-publish)")

    # 🚨급 신호가 뜬 날만 푸시 (NTFY_TOPIC 설정 시)
    alerts = alert_lines(data_md)
    if alerts:
        push("\n".join(alerts), title="Morning Brief Signal",
             click_url=result["notion_url"])

    return result


def run(memo: str = "", publish: bool = True, save_local: bool = True) -> dict:
    """오후 투자 일지 — 한국 장 마감 후, 내 메모와 함께 실행."""
    today = _date.today().isoformat()
    thesis = load_thesis()

    print(f"\n📊 [1/4] 시장 데이터 수집 중... ({today}, 한국 장 마감 반영)")
    ctx, data_md = _collect()
    print(data_md)

    brief = load_brief(today)
    if brief:
        print("\n🔁 [2/4] 아침 브리핑의 Grok 분석 재사용 (재실행 없음)")
        analysis = brief["analysis"]
    else:
        print("\n🔍 [2/4] Grok - 시장·테크 분석 중... (아침 브리핑 없음 → 즉석 실행)")
        analysis = analyze_market(today, data_md, thesis=thesis)
        print(analysis[:500] + ("..." if len(analysis) > 500 else ""))

    trades = load_trades()
    if trades:
        print(f"  🧾 최근 매매 기록 반영 ({len(trades.splitlines())}건)")
    print("\n✍️ [3/4] Claude - 투자 일지 작성 중...")
    journal = write_journal(today, data_md, analysis, memo, thesis=thesis, trades=trades)

    # 차트는 일지 생성 후에 붙인다 (LLM 토큰 소모 없음, Notion에서 이미지로 렌더)
    charts_md = charts.charts_markdown(ctx)
    if charts_md:
        journal += "\n\n## 차트\n" + charts_md

    result = {"date": today, "journal": journal, "notion_url": "", "local_path": ""}

    if save_local:
        result["local_path"] = _save_local(f"{today}.md", journal)
        print(f"💾 로컬 저장: {result['local_path']}")

    if publish:
        print("\n📤 [4/4] Notion 발행 중...")
        url = publish_page(f"📈 투자 일지 — {today}", journal)
        result["notion_url"] = url
        print(f"✅ 발행 완료: {url}")
    else:
        print("\n⏭️ [4/4] Notion 발행 건너뜀 (--no-publish)")

    return result
