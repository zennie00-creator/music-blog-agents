# DEVLOG

일지 에이전트 개발 기록.

## 2026-07-19 (6) — 뉴스·오피니언 소스 지정 (sources.md)

- 오해 정리: CNN은 뉴스가 아니라 공포·탐욕 지수 전용. 뉴스 수집은 Grok
  라이브 검색 담당인데, 지금까지는 '어디를 볼지' 지정이 없었음.
- `sources.md` (gitignore, example 커밋): 우선 참고 매체 + X 계정 + 뉴스레터.
  기본 라인업(벤치마크): Bloomberg/CNBC/Reuters/WSJ/FT + 국내(연합인포맥스 등),
  X는 @markminervini(모멘텀/스테이지), @dylan522p(SemiAnalysis 반도체),
  @dnystedt(아시아 반도체), @charliebilello, @LizAnnSonders, @KobeissiLetter,
  뉴스레터는 SemiAnalysis·The Transcript.
- 주입 경로 2개: ① 소스 전체 텍스트를 Grok 시스템 프롬프트에 '우선 참고'로,
  ② X 핸들은 xAI search_parameters의 `included_x_handles`로 직접 전달
  (최대 10개, 스키마 거절 시 기본 검색 자동 폴백 — core/llm.py).
- 모닝 브리핑에 '## 주요 목소리' 섹션 추가: 지정 계정·뉴스레터의 지난 24시간
  핵심 발언 2~4개 (발언자 명시). --ask/--discuss의 Grok 호출에도 동일 적용.
- 페이월(블룸버그 등) 원문 스크래핑은 하지 않음 — Grok 검색이 헤드라인·요지
  수준에서 반영. Substack도 공개 글 위주.
- 참고: Minervini의 VCP(변동성 수축 + 거래량 드라이업 후 돌파)는 반등품질/RS
  신호와 철학이 맞닿음 — 'VCP 수축 감지'를 향후 신호 후보로 기록.

## 2026-07-19 (5) — 하루 두 번 리듬 + GitHub Actions 배포

### 아침/오후 분리 (pipeline.py)
- `run_brief()` 아침 (미장 마감 후): 데이터·신호 + Grok 분석·전제 보드 →
  📊 모닝 브리핑 발행. **Claude 호출 없음** (브리핑은 대시보드+신호+Grok으로 충분).
  Grok 분석을 `journals/.brief-날짜.json`에 저장.
- `run()` 오후 (한국장 마감 후): 데이터 재수집(한국장 반영) + **아침 Grok 분석
  재사용**(재실행 없음) + 내 메모 → Claude가 📈 투자 일지 작성·발행.
  아침 브리핑이 없으면 Grok 즉석 실행으로 폴백.
- CLI: `--brief` 추가.

### 배포 (.github/workflows/daily-invest.yml)
- 모닝 브리핑: cron UTC 월~금 21:30 = KST 화~토 06:30 자동.
- 투자 일지: workflow_dispatch (memo 입력) 또는 로컬 실행.
- TZ=Asia/Seoul (러너 UTC 날짜 밀림 방지). Secrets 4개 필요.
- 주의: Actions 러너는 매 실행 초기화 → 오후 일지를 Actions로 돌리면 아침
  분석 재사용이 안 되고 Grok을 한 번 더 부른다 (로컬 실행은 재사용됨).
- 미결: thesis.md/portfolio.md는 gitignore 상태라 Actions에선 기본 구성으로
  동작. 반영하려면 커밋(우선 후보) 또는 Secrets 주입 — 사용자 결정 대기.

### 벤치마크 제안 (디스커션에서 제안, 구현 대기)
1. 신호 이력 로그 + 사후 검증 (신호의 성적표) ← 최우선 추천
2. 주간 회고 리뷰 (--weekly)
3. 신호 있는 날만 푸시 알림 (텔레그램/ntfy.sh)
4. 매매 기록 trades.md (plan vs action 갭 점검)
5. 데이터 소스 이중화 (stooq fallback)

## 2026-07-19 (4) — 토론 이어하기(토큰 최소화) + 시각화

### 토론 상태 지속 · 토큰 설계 (discussion.py 재작성)
- 매 라운드 전체 대화 재전송 → **롤링 요약 + 최근 6개 발언 원문**만 전송.
  발언 12개 초과 시 오래된 부분을 요약으로 흡수 (Claude 호출 1회/6발언).
- 상태는 `discussions/<주제>.json`에 라운드마다 저장 (중간에 끊겨도 안전).
  `--discuss "주제"` = 같은 주제 이어하기, `--discuss` (주제 생략) = 최근 토론 재개.
- '종료' 시 insights.md 아카이브 + 상태는 유지 (계속 이어갈 수 있음).

### 시각화 (charts.py)
- 대시보드 표에 **60일 스파크라인** 컬럼 (유니코드 8단계 — LLM 토큰 부담 미미,
  Grok/Claude도 추세 모양을 읽을 수 있음).
- Notion 발행 시 지수·섹터·주도주 자산의 **종가 라인 + 거래량 바 차트** 이미지
  자동 첨부 (QuickChart — 키·의존성 불필요, chart.js 설정을 URL에 담아 렌더).
  차트는 일지 '생성 후' 붙이므로 LLM 토큰 소모 없음. 채권·환율은 차트 제외
  (커브 신호가 커버). core/notion.py에 `![...](url)` → image 블록 변환 추가.
- `--check`에는 미포함 — quickchart.io 접근이 안 되면 Notion에서 이미지가
  깨져 보이는 것으로 확인 가능.

## 2026-07-19 (3) — 자산군 계층 · 금리 커브 · RS · 전제 기둥 · 삼자 토론

디스커션에서 확정된 설계 반영:

### 포트폴리오/전제 분리
- `portfolio.md` (워치리스트, 자산군 섹션 구조) ↔ `thesis.md` (투자 전제) 분리.
  둘 다 gitignore, `*.example.md` 커밋.
- 자산군: 채권(미 2/10/20/30년 + 한국 10년) / 금 / 지수(미국·한국·중국) /
  변동성·환율 / 섹터 / 주도주 / 크립토. 대시보드도 구분 컬럼으로 그룹화.
- 주도주는 `@벤치마크` 표기 (예: `nvda.us: 엔비디아 @^sox`) → RS 신호 대상.
- 멀티소스: stooq 기본 + `naver/000660` 형식으로 네이버 금융(한국 개별 종목).
  SK하이닉스는 나스닥 상장 2주라 데이터 부족 → 코스피 원주로 추적.

### 새 신호
- `yield_curve.py`: 2s10s(역전=침체 경계, 해소 국면이 더 위험), 10s30s,
  한미 10년 금리차(역전 폭 확대=자본 유출 압력). 20거래일 전 대비 방향 표시.
  전제의 '금리 기둥'을 정량으로 매일 대조.
- `relative_strength.py`: RS(종목/벤치마크 가격 비율 — 거래량은 안 들어감) 추세
  + 매집/분산 비율(상승일 거래량÷하락일 거래량) 병행. 주도주 이탈(RS↓+분산)은
  천장 선행 경보, 주도주 선회복은 진성 반등 방증. 데이터 부족 종목은 판정 보류 표시.
  엣지 수정: 연속 하락(acc=0.0 falsy) / 연속 상승(하락일 거래량 0 → ∞ 매집).

### 전제 기둥 구조
- thesis.example.md를 기둥 구조로 재작성: 금리 / 유동성 / 리딩 산업 업황
  + New Trends(관찰 중, 승격 조건 명시. 예: 미·중 AI 패권 → 미 정부 지분투자).
- Grok 분석에 '전제 상태 보드' 추가: 기둥별 🟢🟡🔴 판정 + 근거 (뉴스 대조).
- 일지 규칙: 전제 유효 시 추세 악화는 '비중 조절 신호', 전제 어긋남은
  기술 신호와 무관하게 구조적 재검토 플래그. 액션 문구는 자산 배분 계층
  (현금/채권/금/주식-미국·한국·기타)에 맞춤.

### 리서치 모드 (인사이트 루프)
- `python invest.py --ask "질문"`: Grok 단발 리서치, insights.md에 자동 아카이브.
- `python invest.py --discuss "주제"`: 나·Grok·Claude 삼자 토론 루프.
  매 라운드: 내 발언 → Grok(라이브 검색, 데이터 담당) → Claude(비판적 검토,
  전제와의 충돌 점검). 종료 시 Claude가 핵심 인사이트 + 프로그램 반영 후보를
  요약하고 전체 대화를 insights.md에 저장.
- 여기서 나온 인사이트를 코드/전제에 반영하는 건 Claude Code 세션에서 (이 파일 기준).

### 확인 필요 (로컬 첫 실행 시)
- stooq 채권 심볼 실제 동작: `2usy.b, 20usy.b, 30usy.b, 10kry.b` (10usy.b는 기존 확인)
- stooq `^shc`(상해종합), `^hsi`(항셍), `^kospi` 거래량 제공 여부
- 네이버 siseJson 응답 파싱 (합성 데이터로는 검증됨)

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
