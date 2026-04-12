import os, anthropic

def curate_music(mood):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    prompt = f"""당신은 감성적이고 인문학적 소양이 깊은 음악 큐레이터입니다.
다음 분위기나 키워드에 가장 잘 어울리는 음악을 딱 하나 선정해주세요:
분위기/키워드: {mood}
아래 형식으로 정확하게 답해주세요:
- 아티스트: [이름]
- 앨범: [앨범명]
- 트랙: [곡명]
- 선정 이유: [2~3문장]"""
    msg = client.messages.create(model="claude-opus-4-6", max_tokens=512,
        messages=[{"role":"user","content":prompt}])
    return msg.content[0].text
