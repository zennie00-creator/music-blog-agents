"""데이터 소스 · API 연결 헬스체크 — `python invest.py --check`

로컬 첫 실행 때 이걸 먼저 돌려서 확인한다:
  [1] API 키 설정 여부
  [2] portfolio.md 워치리스트의 심볼별 시세 수집 (행 수·기간·거래량 유무)
  [3] 심리 지표 (CNN 공포·탐욕, CBOE Put/Call)
  [4] LLM·Notion 실연결 (소액 ping 호출)
"""
import requests

from core import config
from core.llm import ask_claude, ask_grok
from modes.investment import portfolio
from modes.investment.market_data import fetch_history, fetch_fear_greed
from modes.investment.signals import put_call


def _ok(msg):
    print(f"  ✅ {msg}")


def _warn(msg):
    print(f"  ⚠️ {msg}")


def _fail(msg):
    print(f"  ❌ {msg}")


def run_check():
    print("\n🔧 투자 일지 헬스체크")

    print("\n[1] API 키 (.env)")
    for name, val in [
        ("ANTHROPIC_API_KEY (Claude — 일지 작성·토론 검토)", config.ANTHROPIC_API_KEY),
        ("XAI_API_KEY (Grok — 분석·리서치)", config.XAI_API_KEY),
        ("NOTION_API_KEY (발행)", config.NOTION_API_KEY),
        ("NOTION_DATABASE_ID (발행 대상 DB)", config.NOTION_DATABASE_ID),
    ]:
        _ok(f"{name}: 설정됨") if val else _fail(f"{name}: 없음")

    print("\n[2] 시세 데이터 (portfolio.md 워치리스트)")
    if config.MARKET_CSV_URLS:
        from modes.investment import sheet_source
        snap = sheet_source.fetch_snapshot()
        if snap:
            _ok(f"구글시트 CSV: {len(snap)}종목 수신 (예: {', '.join(list(snap)[:3])} …)")
        else:
            _fail("구글시트 CSV: 0종목 — URL·게시 설정 확인 (웹에 게시 → CSV 인지)")
    else:
        _warn("MARKET_CSV_URLS 미설정 — 미국 시세는 gsheet/ 심볼로 안 들어옴")
    sections, _ = portfolio.load()
    for title, items in sections:
        print(f"  — {title}")
        for sym, name in items:
            hist = fetch_history(sym)
            if not hist:
                _fail(f"{name} ({sym}): 수집 실패 — 심볼 확인 필요")
            elif len(hist) < 30:
                _warn(f"{name} ({sym}): {len(hist)}행 — 데이터 부족 (신호 판정 제한적)")
            else:
                has_vol = any(r["volume"] for r in hist[-15:])
                note = "" if has_vol else " · 거래량 없음 → 다이버전스/반등/RS 제외 (시세·커브는 정상)"
                _ok(f"{name} ({sym}): {len(hist)}행, {hist[0]['date']} ~ {hist[-1]['date']}{note}")

    print("\n[3] 심리 지표")
    fg = fetch_fear_greed()
    _ok(f"CNN 공포·탐욕: {fg['score']} ({fg['rating']})") if fg else _fail("CNN 공포·탐욕: 수집 실패")
    ratios, err = put_call.fetch()
    if ratios:
        _ok(f"CBOE Put/Call: {ratios}")
    else:
        _fail(f"CBOE Put/Call: 수집 실패 ({err}) — 엔드포인트 확인 필요")

    print("\n[4] LLM · Notion 연결 (소액 ping)")
    if config.XAI_API_KEY:
        try:
            ask_grok("짧게 답하세요.", "연결 확인용입니다. 'ok'라고만 답하세요.",
                     live_search=False, max_tokens=10)
            _ok(f"Grok ({config.GROK_MODEL}) 연결됨")
        except Exception as e:
            _fail(f"Grok 호출 실패: {e}")
            print("  🔬 Grok 원인 진단 (엔드포인트별 원응답):")
            from core.llm import grok_diagnose
            grok_diagnose()
    else:
        _warn("Grok: 키 없음 — https://console.x.ai 에서 발급 후 .env의 XAI_API_KEY에 설정")

    if config.ANTHROPIC_API_KEY:
        try:
            ask_claude("짧게 답하세요.", "연결 확인용입니다. 'ok'라고만 답하세요.", max_tokens=2048)
            _ok(f"Claude ({config.CLAUDE_MODEL}) 연결됨")
        except Exception as e:
            _fail(f"Claude 호출 실패: {e}")
    else:
        _warn("Claude: 키 없음 — https://console.anthropic.com 에서 발급")

    if config.NOTION_API_KEY and config.NOTION_DATABASE_ID:
        try:
            r = requests.get(
                f"https://api.notion.com/v1/databases/{config.NOTION_DATABASE_ID}",
                headers={
                    "Authorization": f"Bearer {config.NOTION_API_KEY}",
                    "Notion-Version": config.NOTION_VERSION,
                },
                timeout=30,
            )
            r.raise_for_status()
            title = "".join(t.get("plain_text", "") for t in r.json().get("title", []))
            _ok(f"Notion DB 연결됨: '{title or '(제목 없음)'}'")
        except Exception as e:
            _fail(f"Notion 접근 실패: {e} — integration이 DB에 연결됐는지 확인")
    else:
        _warn("Notion: 키/DB ID 없음 — 발행 단계는 --no-publish로 건너뛸 수 있음")

    print("\n헬스체크 끝. ❌ 심볼은 portfolio.md에서 수정하거나 삭제하면 된다.\n")
