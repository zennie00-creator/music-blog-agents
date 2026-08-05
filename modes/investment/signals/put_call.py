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
        "https://cdn.cboe.com/api/global/delayed_quotes/put_call_ratios.json",
        "https://cdn.cboe.com/data/us/options/market_statistics/daily/all_daily_statistics.json",
        f"https://www.cboe.com/us/options/market_statistics/daily/?dt={ymd}",
        "https://www.cboe.com/us/options/market_statistics/",
    ]


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
        m = re.search(rf"{label}[^<>]{{0,40}}?put[/\s]*call[^<>]{{0,40}}?"
                      r"(\d\.\d{2})", text, re.I | re.S)
        if m:
            v = float(m.group(1))
            if 0 < v < 5:
                out[key] = v
    return out


def fetch():
    last_err = None
    for url in _endpoints():
        try:
            r = requests.get(url, headers=_UA, timeout=30)
            r.raise_for_status()
            body = r.text
            try:
                ratios = _parse(r.json())
            except ValueError:      # JSON이 아니면 HTML로 시도
                ratios = _parse_html(body)
            if ratios:
                print(f"  ✅ Put/Call 소스 확보: {url.split('//')[-1][:60]}")
                return ratios, None
            last_err = f"{url.split('//')[-1][:50]}: 200이지만 비율을 찾지 못함"
        except Exception as e:
            last_err = f"{url.split('//')[-1][:50]}: {type(e).__name__} {str(e)[:60]}"
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
