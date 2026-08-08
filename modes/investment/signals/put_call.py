"""옵션 심리 — CBOE Put/Call Ratio.

풋/콜 비율은 시장 심리의 역발상 지표:
- Total P/C가 1.1 위로 치솟으면 공포 과다 → 역발상 관점의 저점권 후보
- 0.7 아래면 콜 쏠림(과열·안일) → 조정 취약 구간

CBOE 공개 데이터를 키 없이 가져온다. 엔드포인트가 막히면 섹션에
실패 사유를 남기고 파이프라인은 계속 진행한다.
"""
import requests

TITLE = "옵션 심리 — Put/Call Ratio"

# CBOE cdn은 브라우저 User-Agent가 없으면 403을 준다.
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
       "Accept": "application/json,text/plain,*/*"}

# 후보 소스 (위에서부터 시도). cdn.cboe.com은 데이터센터 IP에 403을 주는 것이
# 확인됐으므로(Actions 로그), www 계열·일자 지정 CSV 등 다른 경로도 함께 시도한다.
# 어느 경로가 러너에서 살아있는지는 실행 로그로 판별된다.
def _endpoints():
    from datetime import date, timedelta
    day = date.today()
    if day.weekday() >= 5:  # 주말이면 직전 금요일자
        day -= timedelta(days=day.weekday() - 4)
    ymd = day.isoformat()
    return [
        # 정적 CSV 아카이브 — 동적 API(/api/)와 경로가 달라 차단 정책도 다를 수 있다.
        # 이쪽이 되면 파싱도 확정적이라 가장 먼저 시도한다.
        f"{_ARCHIVE}/totalpc.csv",
        f"{_ARCHIVE}/equitypc.csv",
        f"{_ARCHIVE}/indexpc.csv",
        f"{_ARCHIVE}/totalpcarchive.csv",
        f"{_ARCHIVE}/equitypcarchive.csv",
        f"{_ARCHIVE}/indexpcarchive.csv",
        "https://cdn.cboe.com/api/global/delayed_quotes/put_call_ratios.json",
        "https://cdn.cboe.com/data/us/options/market_statistics/daily/all_daily_statistics.json",
        f"https://www.cboe.com/us/options/market_statistics/daily/?dt={ymd}",
        "https://www.cboe.com/us/options/market_statistics/",
    ]


_ARCHIVE = "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios"

# CSV 파일명 → 라벨. 파일 하나가 한 종류의 비율만 담으므로 URL로 라벨이 정해진다.
_CSV_LABELS = [("total", "total_ratio"), ("equity", "equity_ratio"),
               ("index", "index_ratio")]


def _parse_csv(text: str, url: str):
    """CBOE 비율 아카이브 CSV → {label: 최신 비율}.

    형식: 안내문 몇 줄 뒤에 DATE,CALL,PUT,TOTAL,P/C Ratio 헤더가 오고 일자별 행이
    이어진다. 헤더 위치가 파일마다 달라 '비율처럼 보이는 마지막 열'을 찾는 대신,
    헤더에서 ratio 열 번호를 잡고 마지막 데이터 행을 읽는다."""
    import csv as _csv
    import io as _io
    key = next((k for name, k in _CSV_LABELS if name in url.lower()), "total_ratio")
    rows = list(_csv.reader(_io.StringIO(text)))
    ratio_col, last_val = None, None
    for row in rows:
        if ratio_col is None:
            # 파일 첫 줄의 안내문("Cboe Volume and Put/Call Ratios")에도 'ratio'가
            # 들어 있어 그걸 헤더로 잡으면 이후 전부 실패한다. 헤더는 열이 여럿이다.
            if len(row) < 3:
                continue
            for i, cell in enumerate(row):
                c = cell.strip().lower()
                if "ratio" in c or c in ("p/c", "pc"):
                    ratio_col = i
                    break
            continue
        if len(row) <= ratio_col:
            continue
        try:
            v = float(row[ratio_col].strip())
        except ValueError:
            continue
        if 0 < v < 5:
            last_val = v          # 파일은 과거→최신 순 — 마지막 값이 최신
    return {key: last_val} if last_val is not None else {}


def _parse(data):
    """엔드포인트별 응답 형태 차이를 흡수해 {label: ratio}를 뽑는다."""
    ratios = {}

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k).lower().replace("-", "_").replace(" ", "_")
                if isinstance(v, (int, float)) and "ratio" in key and 0 < v < 5:
                    ratios[key] = float(v)
                else:
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return ratios


def _parse_html(text):
    """HTML 페이지에서 'Total Put/Call Ratio 0.93' 형태의 값을 찾는다."""
    import re
    out = {}
    for label, key in (("total", "total_ratio"), ("index", "index_ratio"),
                       ("equity", "equity_ratio")):
        # 라벨과 숫자 사이에는 보통 태그가 낀다("...Ratio</span><span>0.93").
        # 태그를 못 넘는 [^<>] 대신 '숫자가 아닌 문자'로 건너뛴다.
        m = re.search(rf"{label}\s*put\s*[/\s-]*\s*call[^0-9]{{0,120}}?"
                      r"(\d\.\d{2})", text, re.I | re.S)
        if m:
            v = float(m.group(1))
            if 0 < v < 5:
                out[key] = v
    return out


def fetch():
    last_err = None
    collected = {}
    for url in _endpoints():
        # CSV 아카이브는 파일 하나가 한 종류(total/equity/index)만 담는다.
        # 첫 성공에서 멈추면 Total만 얻고 끝나므로, CSV끼리는 모아서 합친다.
        is_csv = url.startswith(_ARCHIVE)
        if collected and not is_csv:
            break                    # CSV로 이미 값을 얻었으면 느린 HTML 경로는 생략
        try:
            r = requests.get(url, headers=_UA, timeout=30)
            r.raise_for_status()
            body = r.text
            if is_csv:
                got = _parse_csv(body, url)
                if got:
                    collected.update(got)
                    print(f"  ✅ Put/Call CSV: {url.rsplit('/', 1)[-1]} → {got}")
                else:
                    last_err = f"{url.rsplit('/', 1)[-1]}: 200이지만 비율 열을 못 찾음"
                continue
            try:
                ratios = _parse(r.json())
            except ValueError:      # JSON이 아니면 HTML로 시도
                ratios = _parse_html(body)
            if ratios:
                print(f"  ✅ Put/Call 소스 확보: {url.split('//')[-1][:60]}")
                return ratios, None
            last_err = f"{url.split('//')[-1][:50]}: 200이지만 비율을 찾지 못함"
            # 200인데 못 찾았다면 원인이 둘이다 — 마크업이 예상과 다르거나(파서 문제),
            # 값을 JS가 채우거나(requests로는 불가). 판별하려면 실물을 봐야 하므로
            # put/call 주변만 발췌해 로그에 남긴다.
            if "cboe.com" in url and "put" in body.lower():
                import re as _re
                snips = _re.findall(r".{40}put[/\s-]*call.{60}", body, _re.I | _re.S)[:2]
                for s in snips:
                    print(f"     ↳ 발췌: {' '.join(s.split())[:150]}")
        except Exception as e:
            last_err = f"{url.split('//')[-1][:50]}: {type(e).__name__} {str(e)[:60]}"
    if collected:
        return collected, None
    return {}, last_err


def _interpret_total(v):
    if v >= 1.1:
        return "😨 공포 과다 — 역발상 관점 저점권 후보"
    if v >= 0.9:
        return "➖ 중립"
    if v >= 0.7:
        return "🙂 낙관 우위"
    return "🔥 콜 쏠림 (과열·안일 — 조정 취약)"


def run(ctx):
    ratios, err = fetch()
    lines = [f"### {TITLE}"]
    if not ratios:
        # 무료 CBOE 소스가 자주 막힌다(403). 브리핑엔 조용히 생략하되,
        # 실패 사유는 실행 로그에 남긴다 — 사유를 버리면 매일 '불가'만 보이고
        # 차단(403)인지 엔드포인트 폐기(404)인지 영영 알 수 없다.
        if err:
            print(f"  🔻 Put/Call 소스 실패 — {err}")
        lines.append("- (옵션 심리 소스 일시 불가 — 오늘은 생략)")
        return "\n".join(lines)

    # total/전체 비율을 우선 찾고, 나머지는 참고로 나열
    total_key = next((k for k in ratios if "total" in k), None)
    if total_key:
        v = ratios[total_key]
        lines.append(f"- Total P/C: {v:.2f} → {_interpret_total(v)}")
    for k, v in ratios.items():
        if k == total_key:
            continue
        label = k.replace("_", " ").replace("ratio", "P/C").strip()
        lines.append(f"- {label}: {v:.2f}")
    return "\n".join(lines)
