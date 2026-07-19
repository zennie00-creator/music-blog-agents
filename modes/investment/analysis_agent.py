"""분석 에이전트 — Grok(xAI)으로 시장·테크 브리핑 + 전제 상태 판정.

기존 make.com 워크플로우의 Perplexity 리서치 단계를 대체한다.
Grok 라이브 검색으로 당일 뉴스·X 반응까지 반영한 분석을 받고,
투자 전제(thesis.md)가 있으면 기둥별로 '깨지는 조건'에 뉴스를 대조해
상태(🟢유효/🟡주의/🔴어긋남)를 판정한다.
"""
from core.llm import ask_grok

SYSTEM_PROMPT = """당신은 거시경제와 테크 산업에 정통한 시장 분석가입니다.
개인 투자자의 하루 투자 일지에 들어갈 브리핑을 작성합니다.

원칙:
- 최신 뉴스와 데이터를 근거로 쓰고, 추측과 사실을 구분하세요.
- 과장 없이 담백하게. 매수/매도 지시가 아니라 맥락 해설을 하세요.
- 한국어로 작성하세요."""

USER_TEMPLATE = """오늘 날짜: {date}

아래는 오늘 수집한 시장 데이터와 신호입니다:

{market_data}
{thesis_block}
이 데이터를 참고하여 오늘의 시장·테크 브리핑을 마크다운으로 작성해 주세요.
신호 섹션(다이버전스·반등 품질·RS·금리 커브 등)에 플래그가 떠 있으면,
그 배경(수급·뉴스)을 찾아 해석을 덧붙여 주세요.

형식:
## 시장 브리핑
(오늘 글로벌 증시·금리·환율 흐름의 핵심 동인 3~5개를 불릿으로. 각 불릿은 2문장 이내)

## 테크 & AI 동향
(오늘 주목할 테크/AI 뉴스 2~4개를 불릿으로. 왜 중요한지 한 줄 포함)
{thesis_section}
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
    return ask_grok(
        SYSTEM_PROMPT,
        USER_TEMPLATE.format(
            date=date,
            market_data=market_data,
            thesis_block=thesis_block,
            thesis_section=thesis_section,
        ),
        live_search=True,
    )
