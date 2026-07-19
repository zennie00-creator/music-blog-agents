"""뉴스·오피니언 소스 설정 — sources.md 로더.

Grok 라이브 검색에게 '어디를 우선 볼지'를 알려준다:
- 소스 텍스트 전체는 프롬프트 가이드로 주입 (우선 참고 매체·뉴스레터)
- X 계정(@핸들)은 xAI 검색 파라미터로도 전달해 해당 계정 발언을 직접 검색

sources.md가 없으면 아래 DEFAULT(벤치마크 기본 라인업)를 쓴다.
"""
import os
import re

from core import config

DEFAULT = """\
## 뉴스 (헤드라인·요지 요약용)
- Bloomberg, CNBC, Reuters, WSJ, FT, Barron's
- 국내: 연합인포맥스, 한국경제 마켓, 매일경제 증권

## X 계정 (지난 24시간 발언 확인)
- @markminervini — 모멘텀/SEPA, 시장 스테이지 판단
- @dylan522p — SemiAnalysis, 반도체·AI 인프라 공급망
- @dnystedt — 아시아 반도체 뉴스
- @charliebilello — 데이터 중심 매크로
- @LizAnnSonders — 매크로 전략 (Schwab)
- @KobeissiLetter — 매크로 헤드라인·유동성

## 뉴스레터·서브스택 (공개 글 위주)
- SemiAnalysis (반도체·AI 인프라 심층)
- The Transcript (실적 콜 핵심 발췌)
"""

MAX_X_HANDLES = 10  # xAI 검색 파라미터 핸들 수 제한


def load_text() -> str:
    path = os.path.join(config.ROOT_DIR, "sources.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return DEFAULT


def x_handles(text: str = None):
    """X 계정 섹션의 @핸들 목록 (@ 제외)."""
    text = text if text is not None else load_text()
    handles = []
    in_x = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            in_x = "X 계정" in s or "x 계정" in s.lower()
            continue
        if in_x:
            m = re.match(r"-\s*@([A-Za-z0-9_]+)", s)
            if m:
                handles.append(m.group(1))
    return handles[:MAX_X_HANDLES]


def prompt_block() -> str:
    """Grok 프롬프트에 넣을 '우선 참고 소스' 블록."""
    return f"[우선 참고 소스 — 검색 시 이 매체·계정·뉴스레터를 먼저 확인]\n{load_text().strip()}"
