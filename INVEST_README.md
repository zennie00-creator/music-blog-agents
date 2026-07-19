# 📈 투자 일지 모드 — 사용 가이드

시장 데이터 수집 → Grok 시장·테크 분석 → Claude 일지 작성 → Notion 발행.
(기존 make.com: 구글시트→Perplexity→Gemini→Slack 를 대체)

## 1. 셋업 (최초 1회)

```bash
cp .env.example .env
open -e .env          # 아래 4개 키 채우고 저장
pip3 install -r requirements.txt
python3 invest.py --check   # 데이터·API 연결 점검
```

`.env`에 넣을 키:

| 키 | 발급처 |
| --- | --- |
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `XAI_API_KEY` | console.x.ai |
| `NOTION_API_KEY` | notion.so/my-integrations |
| `NOTION_DATABASE_ID` | 아래 Notion 셋업 참고 |

## 2. 명령어

| 명령 | 설명 |
| --- | --- |
| `python3 invest.py --check` | 데이터 소스·API 연결 헬스체크 |
| `python3 invest.py --brief` | 📊 아침 모닝 브리핑 (데이터+신호+Grok, Claude 없음) |
| `python3 invest.py --memo "..."` | 📈 오후 투자 일지 (메모 + Claude 작성) |
| `python3 invest.py --no-publish` | Notion 없이 로컬(`journals/`)에만 저장 |
| `python3 invest.py --ask "질문"` | Grok 단발 리서치 (insights.md 기록) |
| `python3 invest.py --discuss "주제"` | 나·Grok·Claude 삼자 토론 (이어하기 지원) |

## 3. 설정 파일 (줄 단위로 자유 편집)

- **`portfolio.md`** — 워치리스트. 자산군 섹션 + 심볼. 소스는 접두사로 자동 분기:
  - (접두사 없음) = **Yahoo Finance** — `^GSPC`(S&P500), `^NDX`(나스닥100),
    `^SOX`(반도체), `NVDA`, `KRW=X`(원달러), `GC=F`(금), `BTC-USD`
  - `fred/` = **FRED 국채금리** — `fred/DGS10`(미10년), `fred/DGS2`(2년) 등
  - `naver/` = **네이버 금융** — 한국 개별 종목, `naver/000660`(SK하이닉스)
  - 주도주는 이름 뒤 `@벤치마크` → 상대강도(RS) 신호 대상 (예: `NVDA: 엔비디아 @^SOX`)
  - **심볼 찾는 법**: finance.yahoo.com 에서 종목 검색 → 이름 옆 괄호 안 티커
- **`thesis.md`** — 투자 전제(기둥: 금리/유동성/산업 + New Trends). 매일 신호를
  이 전제에 비춰 해석하고, Grok이 기둥별 🟢🟡🔴 상태를 판정.
- **`sources.md`** — Grok이 우선 참고할 뉴스·X 계정·뉴스레터.

## 4. Notion 셋업

1. Notion에서 **데이터베이스(표)** 생성 (일반 페이지 ❌). 페이지 안에서
   `/database` → "표 보기" → "+ 새 데이터베이스".
2. 그 표를 전체 페이지로 연 URL에서 `?v=` **앞의 32자리**가 `NOTION_DATABASE_ID`.
3. 표 우상단 `···` → **연결(Connections)** → 만든 integration 선택. ← 필수!
   (안 하면 발행이 400/403으로 실패)

## 5. 하루 리듬 & 배포

- **아침** (미장 마감 후 ~06:30): 모닝 브리핑 자동 발행
- **오후** (한국장 마감 후): 메모와 함께 투자 일지 작성

GitHub Actions(`.github/workflows/daily-invest.yml`)로 아침 브리핑 자동화:
repo Settings → Secrets에 키 4개 등록 → 화~토 06:30 KST 자동 실행.
오후 일지는 로컬에서 `--memo`로 실행하는 것을 권장 (아침 분석 재사용 → 비용 절감).

## 신호 (매일 자동 판정)

| 신호 | 무엇을 보나 |
| --- | --- |
| 금리 커브 | 2s10s·10s30s 역전 (침체 선행), 한미 금리차 |
| 가격-거래량 다이버전스 | 약세 다이버전스 = 비중 축소 검토 |
| 반등 품질·RSI·H&S | 조정 후 반등이 진성인지 데드캣/우측어깨 위험인지 |
| 주도주 RS·수급 | 주도주 이탈(천장 선행) / 선회복(진성 반등 방증) |
| Put/Call | 옵션 심리 역발상 지표 |

## 문제 해결

- 특정 심볼 ❌ → `portfolio.md`에서 심볼 수정/삭제 (Yahoo 티커 확인)
- Notion 400/403 → 데이터베이스인지 확인 + integration 연결 확인
- 상세 개발 이력은 `DEVLOG.md`
