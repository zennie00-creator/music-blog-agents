"""작성 중이던 일지를 세션 끊김에서 복구하기 위한 초안 저장소.

Streamlit 세션 상태는 네트워크가 길게 끊기면 서버가 세션을 버리면서
사라진다. 진행 상태를 JSON 파일로 자동 저장해 두었다가
대문 화면에서 '이어서 하기'로 복구한다.

한계: 앱 컨테이너가 재부팅/잠들면 파일도 사라진다.
"""
import os
import json
import time

_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".draft_state.json")
MAX_AGE_H = 24  # 이보다 오래된 초안은 무시


def _read_all():
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save(mode, data):
    """모드별 초안 저장 (기존 다른 모드 초안은 유지)."""
    alld = _read_all()
    alld[mode] = {**data, "_saved_at": time.time()}
    try:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(alld, f, ensure_ascii=False)
    except Exception:
        pass  # 저장 실패가 앱을 죽이면 안 된다


def load(mode):
    d = _read_all().get(mode)
    if not d or time.time() - d.get("_saved_at", 0) > MAX_AGE_H * 3600:
        return None
    return d


def clear(mode):
    alld = _read_all()
    if mode in alld:
        alld.pop(mode)
        try:
            with open(_PATH, "w", encoding="utf-8") as f:
                json.dump(alld, f, ensure_ascii=False)
        except Exception:
            pass


def age_minutes(d):
    return int((time.time() - d.get("_saved_at", time.time())) / 60)
