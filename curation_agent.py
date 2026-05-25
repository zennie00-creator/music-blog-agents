import os, anthropic

SYSTEM_PROMPT = """당신은 감성적이고 인문학적 소양이 깊은 음악 큐레이터입니다.
사용자의 분위기/키워드에 맞는 음악을 추천하기 위해 먼저 취향을 파악하고 대화합니다.

진행 방식:
1. 사용자의 키워드를 받으면 먼저 1~2개의 짧고 친근한 질문으로 취향을 파악하세요.
   (예: 선호 장르, 시대, 언어, 보컬 유무, 빠르기 등)
2. 취향이 파악되면 3곡을 추천하세요. 반드시 아래 형식을 정확히 사용하세요.
   장르 필드는 반드시 포함하세요 (classical / non-classical 중 하나):

[SONGS]
1.
아티스트: [이름]
앨범: [앨범명]
트랙: [곡명]
장르: [classical 또는 non-classical]
이유: [2문장으로 선정 이유]

2.
아티스트: [이름]
앨범: [앨범명]
트랙: [곡명]
장르: [classical 또는 non-classical]
이유: [2문장으로 선정 이유]

3.
아티스트: [이름]
앨범: [앨범명]
트랙: [곡명]
장르: [classical 또는 non-classical]
이유: [2문장으로 선정 이유]
[/SONGS]

3. 사용자가 마음에 들지 않는다고 하면, 무엇이 문제인지 한두 가지 질문으로 파악한 뒤 새 3곡을 추천하세요.
4. 이미 추천한 곡은 절대 다시 추천하지 마세요.
5. 한국어로 대화하되 친근하고 따뜻한 말투를 사용하세요.
6. 질문은 간결하게, 한 번에 너무 많이 묻지 마세요.
7. 사용자가 특정 연주자/아티스트를 언급하면, 반드시 그 연주자의 음반만 추천하세요.
   아티스트 필드에 반드시 그 연주자 이름을 넣으세요. (예: "임윤찬 거로" → 아티스트: 임윤찬)"""


def chat_curation(mood, messages):
    """
    messages: [{"role": "user"|"assistant", "content": str}, ...]
    첫 호출 시 messages는 빈 리스트.
    Returns: (response_text, options_list_or_None)
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    if not messages:
        api_messages = [{"role": "user", "content": f"오늘의 분위기/키워드: {mood}"}]
    else:
        api_messages = messages

    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=api_messages
    )
    response = msg.content[0].text

    options = None
    if "[SONGS]" in response and "[/SONGS]" in response:
        songs_text = response.split("[SONGS]")[1].split("[/SONGS]")[0]
        options = _parse_options(songs_text)

    return response, options


def _parse_options(text):
    options = []
    current = {}
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line in ("1.", "2.", "3."):
            if current:
                options.append(current)
            current = {}
        elif line.startswith("아티스트:"):
            current["artist"] = line.split(":", 1)[-1].strip()
        elif line.startswith("앨범:"):
            current["album"] = line.split(":", 1)[-1].strip()
        elif line.startswith("트랙:"):
            current["track"] = line.split(":", 1)[-1].strip()
        elif line.startswith("장르:"):
            current["genre"] = line.split(":", 1)[-1].strip().lower()
        elif line.startswith("이유:"):
            current["reason"] = line.split(":", 1)[-1].strip()
    if current:
        options.append(current)
    return options


def get_album_versions(artist, track, genre):
    """
    모든 장르에서 특정 곡의 다양한 앨범/버전 3개 반환.
    클래식: 연주자/지휘자가 다른 음반
    기타 장르: 스튜디오/라이브/컴필레이션/리마스터 등 다른 수록 앨범
    반환 형식: [{"album": str, "version_info": str, "feature": str}, ...]
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    if genre == "classical":
        prompt = f"""다음 클래식 작품의 대표적인 음반 3개를 추천해주세요.
각 음반은 서로 다른 연주자/지휘자/오케스트라여야 합니다.

작곡가: {artist}
작품: {track}

반드시 아래 형식으로 답해주세요:

[VERSIONS]
1.
앨범명: [앨범명 또는 레이블+녹음연도]
버전정보: [지휘자/연주자 + 오케스트라/앙상블]
특징: [이 연주만의 특징 1~2문장]

2.
앨범명: [앨범명 또는 레이블+녹음연도]
버전정보: [지휘자/연주자 + 오케스트라/앙상블]
특징: [이 연주만의 특징 1~2문장]

3.
앨범명: [앨범명 또는 레이블+녹음연도]
버전정보: [지휘자/연주자 + 오케스트라/앙상블]
특징: [이 연주만의 특징 1~2문장]
[/VERSIONS]"""
    else:
        prompt = f"""다음 곡이 수록된 대표적인 앨범 또는 버전 3가지를 추천해주세요.
스튜디오 원본, 라이브 앨범, 컴필레이션, 리마스터, 싱글, EP 등 다양한 형태를 포함해도 됩니다.

아티스트: {artist}
곡명: {track}
장르: {genre}

반드시 아래 형식으로 답해주세요:

[VERSIONS]
1.
앨범명: [앨범명]
버전정보: [스튜디오/라이브/컴필레이션/리마스터 등 + 발매연도]
특징: [이 버전만의 특징 1~2문장]

2.
앨범명: [앨범명]
버전정보: [버전 종류 + 발매연도]
특징: [이 버전만의 특징 1~2문장]

3.
앨범명: [앨범명]
버전정보: [버전 종류 + 발매연도]
특징: [이 버전만의 특징 1~2문장]
[/VERSIONS]"""

    msg = client.messages.create(
        model="claude-haiku-4-5", max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    response = msg.content[0].text

    versions = []
    if "[VERSIONS]" in response and "[/VERSIONS]" in response:
        text = response.split("[VERSIONS]")[1].split("[/VERSIONS]")[0]
        current = {}
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if line in ("1.", "2.", "3."):
                if current:
                    versions.append(current)
                current = {}
            elif line.startswith("앨범명:"):
                current["album"] = line.split(":", 1)[-1].strip()
            elif line.startswith("버전정보:"):
                current["version_info"] = line.split(":", 1)[-1].strip()
            elif line.startswith("특징:"):
                current["feature"] = line.split(":", 1)[-1].strip()
        if current:
            versions.append(current)
    return versions


# 하위 호환성
def curate_music(mood):
    _, options = chat_curation(mood, [])
    if not options:
        return ""
    o = options[0]
    return f"- 아티스트: {o.get('artist','')}\n- 앨범: {o.get('album','')}\n- 트랙: {o.get('track','')}\n- 선정 이유: {o.get('reason','')}"
