"""Whoop API 연동 — OAuth2 인증 + 운동/회복 데이터 수집.

실제 연동에 필요한 환경변수:
  WHOOP_CLIENT_ID       Whoop 개발자 앱의 Client ID
  WHOOP_CLIENT_SECRET   Whoop 개발자 앱의 Client Secret
  WHOOP_REDIRECT_URI    등록한 Redirect URI (기본: http://localhost:8501)

자격증명이나 토큰이 없으면 데모용 샘플 데이터를 반환하므로,
Whoop 계정 없이도 앱 전체 흐름을 테스트할 수 있다.

토큰은 프로젝트 루트의 .whoop_token.json 에 저장된다 (반드시 .gitignore).
"""
import os
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

try:
    import requests
except ImportError:  # requests 미설치 시에도 데모 모드로 동작
    requests = None

AUTH_URL   = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL  = "https://api.prod.whoop.com/oauth/oauth2/token"
API_BASE   = "https://api.prod.whoop.com/developer"
TOKEN_PATH = os.path.join(os.path.dirname(__file__), ".whoop_token.json")

SCOPES = "read:workout read:recovery read:profile offline"

# Whoop sport_id → 한글 종목명 (sport_name이 없을 때만 쓰는 예비 매핑)
SPORT_NAMES = {
    -1: "운동", 0: "러닝", 1: "사이클링", 16: "야구", 17: "농구",
    18: "복싱", 22: "댄스", 27: "미식축구", 29: "골프", 30: "하키",
    33: "유도", 36: "필라테스", 39: "럭비", 42: "스키", 43: "축구",
    44: "스쿼시", 45: "수영", 47: "테니스", 48: "육상", 52: "하이킹",
    62: "역도", 63: "웨이트 트레이닝", 66: "요가", 71: "스피닝",
    101: "걷기",
}

# Whoop sport_name(문자열) → 한글. 없으면 원문을 그대로 보여준다.
SPORT_NAME_KO = {
    "running": "러닝", "walking": "걷기", "cycling": "사이클링",
    "swimming": "수영", "weightlifting": "웨이트 트레이닝",
    "functional_fitness": "펑셔널 트레이닝", "hiit": "HIIT",
    "yoga": "요가", "pilates": "필라테스", "hiking/rucking": "하이킹",
    "hiking": "하이킹", "elliptical": "일립티컬", "rowing": "로잉",
    "spin": "스피닝", "spinning": "스피닝", "tennis": "테니스",
    "basketball": "농구", "soccer": "축구", "golf": "골프",
    "boxing": "복싱", "dance": "댄스", "stairmaster": "스테어마스터",
    "jump_rope": "줄넘기", "climbing": "클라이밍", "skiing": "스키",
    "snowboarding": "스노보드", "pickleball": "피클볼",
    "strength_trainer": "근력 운동", "meditation": "명상",
}


def _redirect_uri():
    return os.environ.get("WHOOP_REDIRECT_URI", "http://localhost:8501")


def has_credentials():
    """Whoop 개발자 앱 자격증명(Client ID/Secret)이 설정돼 있는지."""
    return bool(os.environ.get("WHOOP_CLIENT_ID") and
                os.environ.get("WHOOP_CLIENT_SECRET"))


# ── OAuth ────────────────────────────────────────────────────────────
def get_auth_url(state="whoopblog"):
    """사용자가 열어 로그인·동의할 Whoop 인증 URL."""
    q = urlencode({
        "client_id": os.environ.get("WHOOP_CLIENT_ID", ""),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
    })
    return f"{AUTH_URL}?{q}"


def exchange_code(code):
    """인증 후 받은 code를 access/refresh 토큰으로 교환한다."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": os.environ.get("WHOOP_CLIENT_ID", ""),
        "client_secret": os.environ.get("WHOOP_CLIENT_SECRET", ""),
        "redirect_uri": _redirect_uri(),
    }
    r = requests.post(TOKEN_URL, data=data, timeout=30)
    r.raise_for_status()
    tok = r.json()
    _save_token(tok)
    return tok


def _save_token(tok):
    tok["_saved_at"] = time.time()
    with open(TOKEN_PATH, "w") as f:
        json.dump(tok, f)


def _load_token():
    try:
        with open(TOKEN_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def _refresh(tok):
    data = {
        "grant_type": "refresh_token",
        "refresh_token": tok.get("refresh_token", ""),
        "client_id": os.environ.get("WHOOP_CLIENT_ID", ""),
        "client_secret": os.environ.get("WHOOP_CLIENT_SECRET", ""),
        "scope": SCOPES,
    }
    r = requests.post(TOKEN_URL, data=data, timeout=30)
    r.raise_for_status()
    newtok = r.json()
    _save_token(newtok)
    return newtok


def _valid_access_token():
    """유효한 access token을 돌려준다. 만료 임박이면 자동 갱신."""
    if requests is None:
        return None
    tok = _load_token()
    if not tok:
        return None
    age = time.time() - tok.get("_saved_at", 0)
    if age > tok.get("expires_in", 3600) - 300:  # 5분 여유
        if tok.get("refresh_token"):
            try:
                tok = _refresh(tok)
            except Exception:
                return None
        else:
            return None
    return tok.get("access_token")


def is_connected():
    """실제 Whoop 계정에 연결돼 있는지 여부."""
    return _valid_access_token() is not None


# ── 데이터 수집 ───────────────────────────────────────────────────────
def _get(path, token, params=None):
    r = requests.get(
        f"{API_BASE}{path}",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _sport_name(w):
    """Whoop이 주는 종목명을 우선 사용, 없으면 id 매핑, 그래도 없으면 '운동'."""
    name = w.get("sport_name")
    if name:
        # "running" → "러닝" 처럼 알려진 건 한글로, 아니면 원문 그대로
        key = name.strip().lower().replace(" ", "_")
        return SPORT_NAME_KO.get(key, name.strip().title())
    return SPORT_NAMES.get(w.get("sport_id"), "운동")


def _zone_minutes(zone_duration):
    """zone_duration(밀리초) → 존별 분. 없으면 빈 dict."""
    if not zone_duration:
        return {}
    out = {}
    for i, key in enumerate([
        "zone_zero_milli", "zone_one_milli", "zone_two_milli",
        "zone_three_milli", "zone_four_milli", "zone_five_milli",
    ]):
        ms = zone_duration.get(key)
        if ms:
            out[f"zone{i}"] = round(ms / 60000, 1)
    return out


def _local_time(iso_str, tz_offset):
    """UTC ISO 문자열 + timezone_offset(예 '+09:00') → 'MM/DD HH:MM' 로컬시각."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if tz_offset and len(tz_offset) >= 6:
            sign = 1 if tz_offset[0] == "+" else -1
            h, m = int(tz_offset[1:3]), int(tz_offset[4:6])
            dt = dt + sign * timedelta(hours=h, minutes=m)
        return dt.strftime("%m/%d %H:%M")
    except Exception:
        return iso_str or ""


def _normalize_workout(w):
    score = w.get("score") or {}
    kj = score.get("kilojoule")
    kcal = round(kj / 4.184) if kj else None
    tz = w.get("timezone_offset")

    duration_min = None
    try:
        s = datetime.fromisoformat(w["start"].replace("Z", "+00:00"))
        e = datetime.fromisoformat(w["end"].replace("Z", "+00:00"))
        duration_min = round((e - s).total_seconds() / 60)
    except Exception:
        pass

    dist = score.get("distance_meter")
    strain = score.get("strain")
    alt = score.get("altitude_gain_meter")
    return {
        "id": w.get("id"),
        "sport": _sport_name(w),
        "start": w.get("start"),
        "end": w.get("end"),
        "local_time": _local_time(w.get("start"), tz),
        "scored": w.get("score_state") == "SCORED",
        "duration_min": duration_min,
        "strain": round(strain, 1) if strain is not None else None,
        "avg_hr": score.get("average_heart_rate"),
        "max_hr": score.get("max_heart_rate"),
        "kcal": kcal,
        "distance_m": round(dist) if dist else None,
        "altitude_gain_m": round(alt) if alt else None,
        "percent_recorded": score.get("percent_recorded"),
        "zones": _zone_minutes(score.get("zone_duration")),
    }


def get_recent_workouts(days=2, limit=25):
    """최근 days일 이내의 운동 목록 (최신순). 연결 안 됐으면 데모 데이터."""
    token = _valid_access_token()
    if not token:
        return _mock_workouts()
    try:
        start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        data = _get("/v2/activity/workout", token, {"start": start, "limit": limit})
        records = [_normalize_workout(w) for w in data.get("records", [])]
        # 점수 있는 운동 먼저, 그 안에서 최신순
        records.sort(key=lambda x: (not x["scored"], x.get("start") or ""), reverse=False)
        records.sort(key=lambda x: x.get("start") or "", reverse=True)
        records.sort(key=lambda x: not x["scored"])  # 점수 없는 건 뒤로
        return records or _mock_workouts()
    except Exception:
        return _mock_workouts()


def get_latest_recovery():
    """가장 최근 회복도 데이터. 연결 안 됐으면 데모 값."""
    token = _valid_access_token()
    if not token:
        return {"recovery": 68, "resting_hr": 52, "hrv": 74, "_mock": True}
    try:
        data = _get("/v2/recovery", token, {"limit": 1})
        rec = (data.get("records") or [{}])[0].get("score", {})
        return {
            "recovery": rec.get("recovery_score"),
            "resting_hr": rec.get("resting_heart_rate"),
            "hrv": round(rec["hrv_rmssd_milli"]) if rec.get("hrv_rmssd_milli") else None,
        }
    except Exception:
        return {}


# ── 데모(샘플) 데이터 ─────────────────────────────────────────────────
def _mock_workouts():
    return [
        {
            "id": "mock-1", "sport": "러닝", "_mock": True,
            "start": "2026-07-06T02:46:00Z", "end": "2026-07-06T03:28:00Z",
            "local_time": "07/06 11:46", "scored": True,
            "duration_min": 42, "strain": 14.8, "avg_hr": 148, "max_hr": 188,
            "kcal": 565, "distance_m": 2390, "altitude_gain_m": 12,
            "percent_recorded": 100,
            "zones": {"zone1": 8.0, "zone2": 7.0, "zone3": 6.3,
                      "zone4": 11.8, "zone5": 9.0},
        },
        {
            "id": "mock-2", "sport": "웨이트 트레이닝", "_mock": True,
            "start": "2026-07-06T10:30:00Z", "end": "2026-07-06T10:56:00Z",
            "local_time": "07/06 19:30", "scored": True,
            "duration_min": 26, "strain": 8.1, "avg_hr": 112, "max_hr": 141,
            "kcal": 190, "distance_m": None, "altitude_gain_m": None,
            "percent_recorded": 100,
            "zones": {"zone1": 14.0, "zone2": 8.0, "zone3": 4.0},
        },
        {
            "id": "mock-3", "sport": "운동", "_mock": True,
            "start": "2026-07-06T00:10:00Z", "end": "2026-07-06T00:17:00Z",
            "local_time": "07/06 09:10", "scored": False,
            "duration_min": 7, "strain": None, "avg_hr": None, "max_hr": None,
            "kcal": None, "distance_m": None, "altitude_gain_m": None,
            "percent_recorded": None, "zones": {},
        },
    ]
