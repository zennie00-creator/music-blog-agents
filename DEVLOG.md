# DEVLOG

일지 에이전트 개발 기록.

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
