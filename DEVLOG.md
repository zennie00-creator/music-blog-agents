# DEVLOG

일지 에이전트 개발 기록.

## 2026-07-19 (2) — 시그널 플러그인 구조 + 반등 품질/RSI/H&S/Put-Call

"봐야 되는 조건은 계속 늘어난다" → 신호를 플러그인 구조로 분리:

```
modes/investment/signals/
  __init__.py      # 레지스트리 (ALL에 모듈 추가하면 일지에 자동 반영)
  divergence.py    # 매도/비중조절 신호 (기존)
  rebound.py       # 재진입 신호: 반등 품질 + RSI + 헤드앤숄더
  put_call.py      # 옵션 심리 (CBOE)
modes/investment/indicators.py  # RSI(Wilder), 국소 고점/저점
```

각 신호 모듈은 `TITLE` + `run(ctx) -> str|None`만 구현하면 된다.
ctx는 market_data.collect_context()가 만드는 공유 데이터(심볼별 히스토리).
신호 하나가 실패해도 다른 신호와 파이프라인은 계속 돈다.

### 반등 품질 (rebound.py) — "다이버전스는 팔 때, 이건 다시 살 때"
- 조정(-5% 이상) 후 반등(+2% 이상) 국면에서:
  반등일 거래량/하락기 거래량 비율 + RSI 회복 수준 + 되돌림 %로
  진성 반등 / 약한 반등(데드캣·우측 어깨 위험, 넥라인 명시) / 혼조 판정
- 바닥 탐색 국면에선 RSI 강세 다이버전스(가격 저점↓ RSI 저점↑) 플래그
- 헤드앤숄더: 최근 세 국소 고점이 어깨-머리-어깨(머리 +2%, 어깨 오차 5% 이내)면
  넥라인 레벨과 현재가 이격 표시
- 합성 데이터로 진성/약함/바닥/H&S 케이스 검증 완료

### Put/Call (put_call.py)
- CBOE 무료 엔드포인트 후보 2개를 순서대로 시도, 응답 구조가 달라도
  "ratio" 키를 재귀 탐색해 흡수. Total P/C ≥1.1 공포 과다 / <0.7 과열 해석.
- ⚠️ 이 세션은 외부망 차단이라 엔드포인트 실검증 못 함 — 로컬 첫 실행 때 확인 필요.

### 투자 전제 (thesis.md)
- 리포 루트에 thesis.md를 두면 (thesis.example.md 참고, gitignore됨)
  일지가 매일의 신호를 장기 전제에 비춰 평가. "전제에 아부하지 말 것" 지시 포함.

### 대시보드
- RSI(14) 컬럼 추가. 히스토리 조회 기간 90→120일 (RSI+60일 신호 계산 여유).

## 2026-07-19 — 가격-거래량 다이버전스 신호 추가

기존 make.com 출력 예시 리뷰 후 반영:
- 가져온 것: 개별 종목 + 거래량이 있는 대시보드 표 (필라델피아 반도체, 엔비디아, 마이크론 기본 포함)
- 걷어낸 것: 과한 헤지펀드 톤 (옵션 매수 권고, 공포 조장 수사) — 일지 프롬프트에서 명시적으로 금지

### 다이버전스 (`modes/investment/divergence.py`)
- 정의: 최근 15거래일 종가·거래량 각각의 최소자승 추세를 비교. 가격 추세와
  거래량 추세가 반대로 움직이면 신호. 임계값: 가격 ±2%, 거래량 ±10%.
- 4가지 판정: 약세 다이버전스(가격↑ 거래량↓ → 비중 조절 검토),
  매도세 둔화(↓↓ → 반등 주시), 하락 가속(↓↑), 건전한 상승(↑↑).
- 배경: 지수 다이버전스가 떴을 때 반도체 일부 현금화 → 재매수 타이밍을
  놓친 경험. 일지가 이 신호를 매일 자동으로 플래그하도록.
- 이를 위해 시세 수집을 당일 스냅숏 → Stooq 일별 히스토리(90일)로 변경.
  등락률도 시가 대비 → 전일 종가 대비로 정확해짐.
- 워치리스트는 `.env`의 `WATCHLIST=심볼:이름,...`으로 교체 가능.
- 합성 데이터로 4개 신호 + 무신호 + 거래량없음 케이스 검증 완료.
  (실제 stooq 심볼 — 특히 ^kospi 거래량 제공 여부 — 는 로컬에서 확인 필요)

## 2026-07-17 — 📈 투자 일지 모드 추가

### 목표
기존 make.com 워크플로우(구글시트 → Perplexity → Gemini → Slack)를 대체하는
투자 일지 파이프라인 구축:

> **시장 데이터 수집 → Grok(xAI) 시장·테크 분석 → Claude가 내 메모와 합쳐 일지 작성 → Notion 발행**

### 구조

```
core/                        # 모드 공통 모듈
  config.py                  # .env 로드 + 설정 (외부 의존성 없이 자체 파싱)
  llm.py                     # ask_claude() / ask_grok()
  notion.py                  # 마크다운 → Notion 블록 변환 + 페이지 발행
modes/
  investment/                # 📈 투자 일지 모드
    market_data.py           # Stooq 시세 + CNN 공포·탐욕 지수 (무료, 키 불필요)
    analysis_agent.py        # Grok 시장·테크 브리핑 (라이브 검색 사용)
    journal_agent.py         # Claude 일지 작성 (메모 중심 편집)
    pipeline.py              # 4단계 오케스트레이션
invest.py                    # CLI 진입점
```

기존 음악 블로그 에이전트(app.py, *_agent.py)는 그대로 두고, 신규 모드는
`core/` + `modes/` 구조로 분리했다. 운동/개발 모드도 같은 자리에 추가하면 된다.

### 실행

```bash
cp .env.example .env   # 키 채우기
pip install -r requirements.txt
python invest.py --memo "오늘 엔비디아 일부 익절, 현금 비중 20%로."
python invest.py --no-publish   # Notion 없이 로컬(journals/)에만 저장
```

### 설계 결정

- **시장 데이터**: Stooq CSV(S&P500·나스닥·다우·코스피·VIX·원달러·BTC·미10년물)와
  CNN Fear & Greed. 둘 다 API 키가 필요 없고, 실패해도 파이프라인은 계속 진행.
  등락률은 당일 시가 대비(전일 종가는 별도 요청이 필요해 생략).
- **Grok**: xAI chat completions를 requests로 직접 호출. `search_parameters: {mode: auto}`로
  라이브 검색을 켜서 당일 뉴스 반영 (Perplexity 대체 이유). 모델은 `GROK_MODEL`로 교체 가능.
- **Claude**: anthropic SDK, 기본 모델 `claude-opus-4-8`, adaptive thinking + 스트리밍.
  프롬프트 원칙: 메모가 중심, 데이터는 재료. 없는 의견을 지어내지 않기.
- **Notion**: SDK 없이 REST 직접 호출. DB의 title 속성 이름을 매번 조회해서
  '이름'/'Name' 어느 쪽이든 동작. 100블록 제한은 append로 분할 처리.
- **백업**: Notion 발행과 별개로 `journals/YYYY-MM-DD.md`에 항상 로컬 저장.

### TODO / 다음 단계
- [ ] 운동 모드, 개발 모드 추가 (같은 core/ 재사용)
- [ ] app.py에 모드 선택 UI 통합 (Streamlit 탭)
- [ ] 스케줄 실행 (매일 장 마감 후 자동 실행 — GitHub Actions cron 등)
- [ ] 보유 종목 워치리스트를 .env 또는 별도 파일로 받아 시세에 포함
