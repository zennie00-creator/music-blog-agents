"""분석 에이전트 — Grok(xAI)으로 시장·테크 브리핑 생성.

기존 make.com 워크플로우의 Perplexity 리서치 단계를 대체한다.
Grok 라이브 검색으로 당일 뉴스·X 반응까지 반영한 분석을 받는다.
"""
from core.llm import ask_grok

SYSTEM_PROMPT = """당신은 거시경제와 테크 산업에 정통한 시장 분석가입니다.
개인 투자자의 하루 투자 일지에 들어갈 브리핑을 작성합니다.

원칙:
- 최신 뉴스와 데이터를 근거로 쓰고, 추측과 사실을 구분하세요.
- 과장 없이 담백하게. 매수/매도 지시가 아니라 맥락 해설을 하세요.
- 한국어로 작성하세요."""

USER_TEMPLATE = """오늘 날짜: {date}

아래는 오늘 수집한 시장 데이터입니다:

{market_data}

이 데이터를 참고하여 오늘의 시장·테크 브리핑을 마크다운으로 작성해 주세요.
데이터에 가격-거래량 다이버전스 신호가 표시되어 있으면, 그 배경(수급·뉴스)을
찾아 해석을 덧붙여 주세요.

형식:
## 시장 브리핑
(오늘 글로벌 증시·금리·환율 흐름의 핵심 동인 3~5개를 불릿으로. 각 불릿은 2문장 이내)

## 테크 & AI 동향
(오늘 주목할 테크/AI 뉴스 2~4개를 불릿으로. 왜 중요한지 한 줄 포함)

## 체크포인트
(향후 며칠 내 주목할 이벤트·지표 2~3개)"""


def analyze_market(date: str, market_data: str) -> str:
    return ask_grok(
        SYSTEM_PROMPT,
        USER_TEMPLATE.format(date=date, market_data=market_data),
        live_search=True,
    )
