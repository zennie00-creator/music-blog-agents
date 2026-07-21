"""분석 에이전트 — Grok(xAI)으로 시장·테크 브리핑 + 전제 상태 판정.

기존 make.com 워크플로우의 Perplexity 리서치 단계를 대체한다.
Grok 라이브 검색으로 당일 뉴스·X 반응까지 반영한 분석을 받고,
투자 전제(thesis.md)가 있으면 기둥별로 '깨지는 조건'에 뉴스를 대조해
상태(🟢유효/🟡주의/🔴어긋남)를 판정한다.
"""
from core import config
from core.llm import ask_claude, ask_grok
from modes.investment import news, sources

SYSTEM_PROMPT = """당신은 거시경제와 테크 산업에 정통한 시장 분석가입니다.
개인 투자자(주도주·반도체·AI 중심, 한국·미국 시장)의 하루 투자 일지 브리핑을 씁니다.

원칙:
- 데이터·신호·뉴스에 근거해 쓰고, 사실과 추측을 구분하세요.
- 과장·클리셰 금지. "관망이 유효하다" 같은 공허한 말 대신 구체적 근거와 조건을 대세요.
- 매매 지시가 아니라 '판단 재료'를 제공하되, 자산군별로 언어를 다르게:
  · 지수 = 추세·국면(상승/횡보/하락) 판단, · 섹터 = 비중 방향(확대/유지/축소),
  · 주도주 = 진입/관망/이탈 관점(신호 근거와 함께).
- 한국어. 불릿은 짧고 밀도 있게."""

USER_TEMPLATE = """오늘 날짜: {date}

아래는 오늘 수집한 시장 데이터와 신호입니다:

{market_data}
{thesis_block}{news_block}
이 데이터·뉴스를 종합해 오늘의 시장·테크 브리핑을 마크다운으로 작성해 주세요.
신호 섹션(다이버전스·반등 품질·RS·금리 커브 등)에 플래그가 떠 있으면,
그 배경(수급·뉴스)과 함의를 반드시 해석해 주세요.

형식:
## 한 줄 요약
(오늘 시장을 한 문장으로. 리스크-온/오프, 핵심 동인 포함)

## 시장 브리핑
(글로벌 증시·금리·환율 흐름의 핵심 동인 3~5개를 불릿으로. 각 2문장 이내, 수치 인용)

## 테크 & AI 동향
(오늘 주목할 테크/AI 뉴스 2~4개. 왜 중요한지·누구에게 영향인지 한 줄)

## 주요 목소리
(위 헤드라인·소스에서 시장 관련 핵심 포인트 2~4개. 출처를 명시.
 재료가 없으면 "특기할 발언 없음")
{thesis_section}
## 오늘의 액션 (자산군별)
(- 지수: 국면 판단 한 줄 / - 섹터(반도체 등): 비중 방향 한 줄 /
 - 주도주: 종목별 진입·관망·이탈 관점 한 줄씩. 반드시 신호·데이터 근거를 붙일 것)

## 체크포인트
(향후 며칠 내 주목할 이벤트·지표 2~3개)"""

THESIS_INPUT = """
아래는 투자자의 장기 투자 전제입니다 (기둥 구조, 각 기둥에 '깨지는 조건' 명시):

{thesis}
"""

THESIS_SECTION = """
## 전제 상태 보드
(전제의 기둥별로 오늘 뉴스·데이터를 '깨지는 조건'에 대조해 판정:
 - 기둥 이름: 🟢유효 / 🟡주의 / 🔴어긋남 — 근거 1~2문장 (근거 없으면 '특이 근거 없음')
 New Trends 항목은 승격 조건 관련 근거가 나왔는지만 확인해 한 줄씩)
"""


def analyze_market(date: str, market_data: str, thesis: str = "") -> str:
    thesis_block = THESIS_INPUT.format(thesis=thesis.strip()) if thesis.strip() else ""
    thesis_section = THESIS_SECTION if thesis.strip() else ""

    # RSS 헤드라인을 미리 수집해 프롬프트에 주입 (Grok 검색 부재 시 뉴스 차원 보강)
    try:
        heads = news.headlines_markdown()
    except Exception as e:
        print(f"  ⚠️ 뉴스 수집 실패 (건너뜀): {e}")
        heads = ""
    news_block = f"\n{heads}\n" if heads else ""

    user = USER_TEMPLATE.format(
        date=date,
        market_data=market_data,
        thesis_block=thesis_block,
        news_block=news_block,
        thesis_section=thesis_section,
    )
    system = SYSTEM_PROMPT + "\n\n" + sources.prompt_block()

    def _claude():
        # RSS 헤드라인은 이미 user에 들어 있으니 그걸 근거로 작성
        note = ("\n\n[안내] 실시간 웹 검색은 없이, 위 시장 데이터·신호·전제와 수집된"
                " 헤드라인만 근거로 작성하세요. 헤드라인에 없는 당일 개별 뉴스는 단정하지 마세요.")
        return ask_claude(system, user + note)

    # Grok가 꺼져 있으면(USE_GROK=0) 바로 Claude — 헛된 재시도·요란한 로그 방지
    if not config.USE_GROK:
        print("  ℹ️ Grok 미사용(USE_GROK=0) → Claude가 뉴스·데이터로 분석")
        return _claude()

    # 1) Grok 라이브 검색 (뉴스·X 반영 — 최선)
    try:
        return ask_grok(system, user, live_search=True, x_handles=sources.x_handles())
    except Exception as e:
        print(f"  ⚠️ Grok 라이브 검색 불가 → 검색 없이 재시도: {e}")

    # 2) Grok 검색 없이 (라이브 검색 API가 원인일 때)
    try:
        return ask_grok(system, user, live_search=False)
    except Exception as e:
        print(f"  ℹ️ Grok 불가 → Claude가 뉴스·데이터로 분석 (정상 동작): {e}")

    # 3) Claude — 수집된 헤드라인+데이터+신호+전제로 작성
    return _claude()
