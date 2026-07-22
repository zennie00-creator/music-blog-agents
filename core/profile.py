"""사용자 프로필(오디오 환경 / 운동 프로필) 저장·로드.

프로필은 프로젝트 루트에 JSON 파일로 저장한다.
Streamlit Cloud는 컨테이너가 재부팅되면 로컬 파일이 사라지므로,
저장할 때 Notion 설정 페이지에도 백업하고(notion_agent.save_settings),
재부팅 직후 로컬 파일이 없으면 Notion 백업에서 되살린다.
"""
import os
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import notion_agent

_BASE = os.path.dirname(os.path.dirname(__file__))

# 각 프로필의 파일명과 기본 스키마
AUDIO_PROFILE = "audio_profile.json"
AUDIO_DEFAULT = {"devices": "", "room": "", "preferences": "", "notes": ""}

WORKOUT_PROFILE = "workout_profile.json"
WORKOUT_DEFAULT = {"goals": "", "sports": "", "tone": "",
                   "style_memory": "", "coach_memory": "", "notes": ""}

# Notion 백업 전체(dict)의 프로세스 내 캐시 — 재부팅 후 첫 로드에만 원격 호출
_remote_cache = None
_remote_loaded = False


def _path(filename):
    return os.path.join(_BASE, filename)


def _remote_settings():
    global _remote_cache, _remote_loaded
    if not _remote_loaded:
        _remote_cache = notion_agent.load_settings() or {}
        _remote_loaded = True
    return _remote_cache


def load(filename, default):
    try:
        with open(_path(filename), encoding="utf-8") as f:
            return {**default, **json.load(f)}
    except Exception:
        pass
    # 로컬 파일이 없으면(재부팅 직후) Notion 백업에서 복원
    remote = _remote_settings().get(filename)
    if isinstance(remote, dict):
        data = {**default, **remote}
        try:
            with open(_path(filename), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return data
    return dict(default)


def save(filename, data):
    """로컬 저장 + Notion 백업. Notion 백업 성공 여부를 반환한다."""
    with open(_path(filename), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    settings = dict(_remote_settings())
    settings[filename] = data
    ok = notion_agent.save_settings(settings)
    if ok:
        global _remote_cache
        _remote_cache = settings
    return ok
