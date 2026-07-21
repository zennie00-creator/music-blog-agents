# 포트폴리오 워치리스트

이 파일을 `portfolio.md`로 복사해 수정하면 기본 구성을 대체한다.
심볼 접두사로 데이터 소스 자동 분기:
- `gsheet/…` 구글시트 웹 게시 CSV (미국 지수·종목·KOSPI — Yahoo 429 우회, Actions에서 안정)
- `fred/…` FRED 국채 금리 (Actions에서 안정, 1일 지연)
- `naver/…` 네이버 금융 (한국 개별 종목)
- (접두사 없음) Yahoo — 로컬에선 되지만 Actions 공용 IP는 429로 막힘

심볼과 이름은 `": "`(콜론+공백)로 구분 — 구글 티커(NASDAQ:NVDA)의 콜론을 보존.
주도주 교체 = 여기서 줄 하나 수정. `@벤치마크`가 붙은 종목은 상대강도(RS) 신호 대상.
※ gsheet 심볼은 게시 CSV(MARKET_CSV_URLS)에 그 티커 줄이 있어야 함(GOOGLEFINANCE).

## 채권 (금리) — 구글시트 CBOE 금리지수 (시트에 INDEXCBOE:* 줄 추가 필요)
gsheet/INDEXCBOE:IRX: 미 3개월(13주)
gsheet/INDEXCBOE:FVX: 미 5년물
gsheet/INDEXCBOE:TNX: 미 10년물
gsheet/INDEXCBOE:TYX: 미 30년물

## 지수 — 미국
gsheet/INDEXSP:.INX: S&P 500
gsheet/INDEXNASDAQ:NDX: 나스닥 100
gsheet/INDEXDJX:.DJI: 다우존스

## 지수 — 한국
gsheet/KRX:KOSPI: 코스피

## 변동성
gsheet/INDEXCBOE:VIX: VIX

## 섹터
gsheet/INDEXNASDAQ:SOX: 필라델피아 반도체

## 주도주 (반도체·AI)
gsheet/NASDAQ:NVDA: 엔비디아 @gsheet/INDEXNASDAQ:SOX
gsheet/NASDAQ:MU: 마이크론 @gsheet/INDEXNASDAQ:SOX
naver/000660: SK하이닉스 @gsheet/KRX:KOSPI
