"""사용자 프로필(오디오 환경 / 운동 프로필) 저장·로드 공통 로직.

프로필은 프로젝트 루트에 JSON 파일로 저장된다.
"""
import os
import json

_BASE = os.path.dirname(os.path.dirname(__file__))

# 각 프로필의 파일명과 기본 스키마
AUDIO_PROFILE = "audio_profile.json"
AUDIO_DEFAULT = {"devices": "", "room": "", "preferences": "", "notes": ""}

WORKOUT_PROFILE = "workout_profile.json"
WORKOUT_DEFAULT = {"goals": "", "sports": "", "tone": "", "notes": ""}


def _path(filename):
    return os.path.join(_BASE, filename)


def load(filename, default):
    try:
        with open(_path(filename), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return dict(default)


def save(filename, data):
    with open(_path(filename), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
