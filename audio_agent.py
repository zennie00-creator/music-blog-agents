import os, anthropic

def get_audio_info(artist, album, track):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    prompt = f"""당신은 감성적인 오디오 전문가입니다.
아티스트: {artist} / 앨범: {album} / 트랙: {track}
2~3문단으로 써주세요:
1. 이 음악의 음향적 특징 (쉬운 말로)
2. 가장 잘 즐길 수 있는 환경 추천
3. 집중해서 들으면 좋을 감상 포인트"""
    msg = client.messages.create(model="claude-opus-4-6", max_tokens=768,
        messages=[{"role":"user","content":prompt}])
    return msg.content[0].text
