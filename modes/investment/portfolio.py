"""포트폴리오 워치리스트 로더 — portfolio.md 파싱.

투자 전제(thesis.md)와 워치리스트(portfolio.md)는 연결되되 분리된 파일이다.
portfolio.md가 없으면 아래 DEFAULT를 쓴다 (portfolio.example.md와 동일).

형식:
  ## 섹션 이름            ← 자산군 구분 (대시보드 그룹, 해석 계층)
  심볼: 표시 이름          ← Yahoo Finance 심볼 (기본, 예: ^GSPC, NVDA, KRW=X)
  fred/DGS10: 이름         ← FRED 국채 금리 (거래량 없음)
  naver/000660: 이름      ← 네이버 금융 소스 (한국 개별 종목)
  NVDA: 엔비디아 @^SOX     ← @벤치마크 가 붙으면 주도주로 간주, RS 신호 대상
"""
import os

from core import config

DEFAULT = """\
## 채권 (금리)
fred/DGS2: 미 2년물
fred/DGS10: 미 10년물
fred/DGS20: 미 20년물
fred/DGS30: 미 30년물

## 금·원자재
GC=F: 금 선물

## 지수 — 미국
^GSPC: S&P 500
^NDX: 나스닥 100
^DJI: 다우존스

## 지수 — 한국
^KS11: 코스피

## 지수 — 중국·기타
000001.SS: 상해종합
^HSI: 항셍

## 변동성·환율
^VIX: VIX
KRW=X: 원/달러

## 섹터
^SOX: 필라델피아 반도체

## 주도주
NVDA: 엔비디아 @^SOX
MU: 마이크론 @^SOX
naver/000660: SK하이닉스 @^KS11

## 크립토
BTC-USD: 비트코인 (USD)
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
