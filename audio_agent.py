import os, json, anthropic

PROFILE_PATH = os.path.join(os.path.dirname(__file__), "audio_profile.json")

def load_audio_profile():
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def get_audio_info(artist, album, track):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    profile = load_audio_profile()
    profile_str = ""
    if any(profile.get(k) for k in ("devices", "room", "preferences", "notes")):
        parts = []
        if profile.get("devices"):
            parts.append(f"청취 기기: {profile['devices']}")
        if profile.get("room"):
            parts.append(f"청취 공간: {profile['room']}")
        if profile.get("preferences"):
            parts.append(f"청취 성향: {profile['preferences']}")
        if profile.get("notes"):
            parts.append(f"기타: {profile['notes']}")
        profile_str = "\n[사용자 오디오 환경]\n" + "\n".join(parts) + "\n"

    prompt = f"""당신은 감성적인 오디오 전문가입니다.
아티스트: {artist} / 앨범: {album} / 트랙: {track}
{profile_str}
2~3문단으로 써주세요:
1. 이 음악의 음향적 특징 (쉬운 말로)
2. 가장 잘 즐길 수 있는 환경 추천{' (위 사용자의 실제 오디오 환경을 기반으로 구체적으로)' if profile_str else ''}
3. 집중해서 들으면 좋을 감상 포인트"""

    msg = client.messages.create(model="claude-opus-4-7", max_tokens=768,
        messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text
