"""포트폴리오 워치리스트 로더 — portfolio.md 파싱.

투자 전제(thesis.md)와 워치리스트(portfolio.md)는 연결되되 분리된 파일이다.
portfolio.md가 없으면 아래 DEFAULT를 쓴다 (portfolio.example.md와 동일).

형식:
  ## 섹션 이름            ← 자산군 구분 (대시보드 그룹, 해석 계층)
  심볼: 표시 이름          ← stooq 심볼 (기본)
  naver/000660: 이름      ← 네이버 금융 소스 (한국 개별 종목)
  nvda.us: 엔비디아 @^sox  ← @벤치마크 가 붙으면 주도주로 간주, RS 신호 대상
"""
import os

from core import config

DEFAULT = """\
## 채권 (금리)
2usy.b: 미 2년물
10usy.b: 미 10년물
20usy.b: 미 20년물
30usy.b: 미 30년물
10kry.b: 한국 10년물

## 금·원자재
xauusd: 금 현물

## 지수 — 미국
^spx: S&P 500
^ndq: 나스닥 100
^dji: 다우존스

## 지수 — 한국
^kospi: 코스피

## 지수 — 중국·기타
^shc: 상해종합
^hsi: 항셍

## 변동성·환율
^vix: VIX
usdkrw: 원/달러

## 섹터
^sox: 필라델피아 반도체

## 주도주
nvda.us: 엔비디아 @^sox
mu.us: 마이크론 @^sox
naver/000660: SK하이닉스 @^kospi

## 크립토
btcusd: 비트코인 (USD)
"""


def load_text() -> str:
    path = os.path.join(config.ROOT_DIR, "portfolio.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return DEFAULT


def parse(text: str):
    """→ (sections, benchmarks)
    sections:   [(섹션명, [(심볼, 이름)])]   — 파일 순서 유지
    benchmarks: {심볼: 벤치마크 심볼}       — @벤치마크가 붙은 항목 (주도주)
    """
    sections = []
    benchmarks = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("# "):
            continue
        if line.startswith("## "):
            current = (line[3:].strip(), [])
            sections.append(current)
            continue
        if current is None or ":" not in line:
            continue
        sym, name = line.split(":", 1)
        sym, name = sym.strip(), name.strip()
        if "@" in name:
            name, bench = name.rsplit("@", 1)
            name = name.strip()
            benchmarks[sym] = bench.strip()
        if sym:
            current[1].append((sym, name or sym))
    return [s for s in sections if s[1]], benchmarks


def load():
    return parse(load_text())
