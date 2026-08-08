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

## 환율
# 금리 다음에 둔다 — 통화는 금리차의 결과라 채권 바로 뒤에서 읽어야 맥락이 이어진다.
# 달러 대비 주요 통화(유로·엔) → 원화 → 달러 자체 순.
# FRED는 Actions IP에서 자주 막혀(market_data._fetch_fred 주석 참조) 쓰지 않는다.
# gsheet(GOOGLEFINANCE)가 이 시스템에서 가장 안정적인 경로라 환율도 여기에 맞춘다.
# ※ EURUSD·USDJPY는 시트에 아래 줄을 추가해야 값이 들어온다 (원/달러는 이미 있음):
#     B열 CURRENCY:EURUSD   C열 =GOOGLEFINANCE(Bn,"price")
#     B열 CURRENCY:USDJPY   C열 =GOOGLEFINANCE(Bn,"price")
gsheet/CURRENCY:EURUSD: 유로/달러 (↑유로 강세)
gsheet/CURRENCY:USDJPY: 달러/엔 (↑엔 약세)
gsheet/CURRENCY:USDKRW: 원/달러 (↑원화 약세)
# 달러 인덱스(DXY)는 GOOGLEFINANCE에 없다. 무료 대안(naver·FRED)이 Actions에서
# 실제로 되는지 `--check`가 매번 시험해 로그로 알려준다 → 되는 쪽을 여기 추가할 것.

## 금
# 자산배분(현금/채권/금/주식)의 한 축인데 그동안 워치리스트에 아예 없었다.
# 달러 바로 밑에 둔다 — 금은 실질금리·달러의 거울이라 함께 읽어야 한다.
#
# 온스당 가격으로 본다. ETF(GLD)는 주당 $398 수준이라 대시보드 숫자가 '금값'으로
# 읽히지 않고, 보수료 때문에 금값과 서서히 벌어져 ×10.8 환산도 가짜 정밀도가 된다.
#
# COMEX 최근월물이 원래 목표였지만 무료로 주는 곳(stooq gc.f, Yahoo GC=F, 네이버)이
# 모두 구글 페처를 막아 시트로 받을 수 없었다. 그래서 현물(XAU/USD)로 간다 —
# COMEX 최근월물과는 베이시스(보관비·금리)만큼, 보통 0.5~1% 안쪽 차이다.
# 추세·비중 판단에는 실질 차이가 없다.
# GOOGLEFINANCE는 귀금속을 아예 지원하지 않는다(CURRENCY:XAUUSD → #N/A, 시트에서
# 직접 확인). 키 없는 시세 JSON을 시트가 대신 받아온다.
#
# ※ 시트 추가 — 티커 칸에 라벨 'XAUUSD'를 직접 쓰고, 가격 칸에:
#     =VALUE(REGEXEXTRACT(TEXTJOIN("",TRUE,
#       IMPORTDATA("https://api.gold-api.com/price/XAU")),"""price"":\s*([0-9.]+)"))
#   (파서는 티커처럼 생긴 라벨이면 무엇이든 받는다 — 대문자·숫자·`:._-` 조합)
# 러너에서 COMEX 선물이 직접 뚫리면(`--check`의 금 프로브) 그쪽으로 교체할 것.
gsheet/XAUUSD: 금 현물 (XAU/USD, $/oz)

## 지수 — 미국
gsheet/INDEXSP:.INX: S&P 500
gsheet/INDEXNASDAQ:NDX: 나스닥 100
gsheet/INDEXDJX:.DJI: 다우존스

## 지수 — 한국
gsheet/KRX:KOSPI: 코스피

## 변동성
gsheet/INDEXCBOE:VIX: VIX

## 에너지 (매크로)
gsheet/NYSEARCA:USO: 원유 ETF(USO·WTI 추종)

## 섹터
gsheet/INDEXNASDAQ:SOX: 필라델피아 반도체

## 주도주 (반도체·AI)
gsheet/NASDAQ:NVDA: 엔비디아 @gsheet/INDEXNASDAQ:SOX
gsheet/NASDAQ:MU: 마이크론 @gsheet/INDEXNASDAQ:SOX
gsheet/NASDAQ:SKHY: SK하이닉스 ADR @gsheet/INDEXNASDAQ:SOX
naver/000660: SK하이닉스 (본주) @gsheet/KRX:KOSPI
gsheet/NYSE:COHR: 코히런트 @gsheet/INDEXNASDAQ:SOX

## 반도체 장비 (브레드스)
gsheet/NASDAQ:ASML: ASML @gsheet/INDEXNASDAQ:SOX
gsheet/NASDAQ:AMAT: 어플라이드 머티어리얼즈 @gsheet/INDEXNASDAQ:SOX
gsheet/NASDAQ:LRCX: 램리서치 @gsheet/INDEXNASDAQ:SOX
gsheet/NASDAQ:KLAC: KLA @gsheet/INDEXNASDAQ:SOX

## 기술주 (관심)
gsheet/NASDAQ:AAPL: 애플
gsheet/NASDAQ:MSFT: 마이크로소프트
gsheet/NASDAQ:GOOGL: 알파벳
gsheet/NASDAQ:TSLA: 테슬라
gsheet/PLTR: 팔란티어 @gsheet/INDEXNASDAQ:NDX
gsheet/NYSE:JOBY: 조비 에비에이션
gsheet/NASDAQ:MSTR: 마이크로스트래티지
gsheet/NASDAQ:COIN: 코인베이스
gsheet/NASDAQ:IBIT: 비트코인 ETF(IBIT)
gsheet/CURRENCY:BTCUSD: 비트코인(BTC)
gsheet/NASDAQ:SPCX: SPCX

# ── 과거 이력을 시트에서 받기 (권장) ────────────────────────────
# 스냅숏 탭은 '오늘 값'만 주므로 이력이 하루 한 줄씩만 쌓인다. stooq·Yahoo 백필은
# 국채·원자재·환율에서 대부분 실패한다(Actions IP 429/차단). 시트에 이력 탭을
# 하나 만들어 게시하면 구글 서버가 대신 받아오므로 차단에 걸리지 않는다.
#
# 새 탭을 만들고 티커 하나당 2열씩 쓴다 (1행 티커, 2행부터 기간 조회):
#   A1: INDEXCBOE:TNX          C1: NYSEARCA:USO
#   A2: =GOOGLEFINANCE(A1,"close",DATE(2019,1,1),TODAY())
#   C2: =GOOGLEFINANCE(C1,"close",DATE(2019,1,1),TODAY())
# 그 탭을 '웹에 게시 → CSV'로 게시하고 URL을 Actions Secrets의
# MARKET_HISTORY_CSV_URLS에 넣으면 backfill이 1순위로 쓴다(쉼표로 여러 개 가능).
# 날짜 로케일은 자동 인식하지만, 확실히 하려면 =TEXT(...,"yyyy-mm-dd")로 감싸도 된다.
#
# 채권(위 gsheet/INDEXCBOE:*)은 시트에 이 줄들을 추가해야 값이 들어온다:
#   B열 티커       C열 =GOOGLEFINANCE(Bn,"price")
#   INDEXCBOE:IRX  INDEXCBOE:FVX  INDEXCBOE:TNX  INDEXCBOE:TYX
#   (금리×10로 나와도 코드가 자동으로 ÷10 보정한다)
#
# 나중에 시트에 줄만 추가하면 자동 반영되는 것들 (GOOGLEFINANCE 티커):
#   gsheet/CURRENCY:USDKRW: 원/달러
#   gsheet/INDEXHANGSENG:HSI: 항셍
