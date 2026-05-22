import os, anthropic

def get_music_info(artist, album, track):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    prompt = f"""당신은 음악과 인문학을 넘나드는 음악 평론가입니다.
아티스트: {artist} / 앨범: {album} / 트랙: {track}
이 음악에 대해 3~4문단으로 써주세요:
1. 아티스트 소개 (시대적 배경, 음악적 뿌리)
2. 앨범이 탄생한 맥락과 의미
3. 이 곡의 감성적·철학적 울림
4. 이 음악을 들어야 하는 이유
전문용어 없이 따뜻한 문체로 써주세요."""
    msg = client.messages.create(model="claude-haiku-4-5", max_tokens=1024,
        messages=[{"role":"user","content":prompt}])
    return msg.content[0].text
