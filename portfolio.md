# 포트폴리오 워치리스트

심볼 접두사로 데이터 소스 자동 분기:
- `gsheet/…` 구글시트 웹 게시 CSV (미국 지수·종목·KOSPI — Yahoo 429 우회, Actions에서 안정)
- `fred/…` FRED 국채 금리 (Actions에서 안정, 1일 지연)
- `naver/…` 네이버 금융 (한국 개별 종목)
- (접두사 없음) Yahoo — 로컬(집 IP)에선 되지만 Actions 공용 IP는 429로 막힘

심볼과 이름은 `": "`(콜론+공백)로 구분 — 구글 티커(NASDAQ:NVDA)의 콜론을 보존.
주도주는 이름 뒤 `@벤치마크`로 RS 신호 대상 지정. 줄 추가/삭제로 가감.
※ gsheet 심볼은 게시 CSV에 그 티커 줄이 있어야 함(GOOGLEFINANCE). 이력은 매일 누적.

## 채권 금리 (CBOE·÷10)
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
gsheet/NASDAQ:SKHY: SK하이닉스 ADR @gsheet/INDEXNASDAQ:SOX
naver/000660: SK하이닉스 (본주) @gsheet/KRX:KOSPI
gsheet/NYSE:COHR: 코히런트 @gsheet/INDEXNASDAQ:SOX

## 환율
gsheet/CURRENCY:USDKRW: 원/달러

## 기술주 (관심)
gsheet/NASDAQ:AAPL: 애플
gsheet/NASDAQ:MSFT: 마이크로소프트
gsheet/NASDAQ:GOOGL: 알파벳
gsheet/NASDAQ:TSLA: 테슬라
gsheet/PLTR: 팔란티어
gsheet/NYSE:JOBY: 조비 에비에이션
gsheet/NASDAQ:MSTR: 마이크로스트래티지
gsheet/NASDAQ:COIN: 코인베이스
gsheet/NASDAQ:IBIT: 비트코인 ETF(IBIT)
gsheet/NASDAQ:SPCX: SPCX

# 채권(위 gsheet/INDEXCBOE:*)은 시트에 이 줄들을 추가해야 값이 들어온다:
#   B열 티커       C열 =GOOGLEFINANCE(Bn,"price")
#   INDEXCBOE:IRX  INDEXCBOE:FVX  INDEXCBOE:TNX  INDEXCBOE:TYX
#   (금리×10로 나와도 코드가 자동으로 ÷10 보정한다)
#
# 나중에 시트에 줄만 추가하면 자동 반영되는 것들 (GOOGLEFINANCE 티커):
#   gsheet/CURRENCY:USDKRW: 원/달러
#   gsheet/INDEXHANGSENG:HSI: 항셍
