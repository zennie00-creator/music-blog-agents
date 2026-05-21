import os
import anthropic
from curation_agent import curate_music
from info_agent import get_music_info
from audio_agent import get_audio_info

def parse_curation(text):
    r = {"artist": "", "album": "", "track": ""}
    for line in text.strip().split("\n"):
        if "아티스트" in line and ":" in line:
            r["artist"] = line.split(":", 1)[-1].strip()
        elif "앨범" in line and ":" in line:
            r["album"] = line.split(":", 1)[-1].strip()
        elif "트랙" in line and ":" in line:
            r["track"] = line.split(":", 1)[-1].strip()
    return r

def write_blog_post(mood):
    print("\n🎵 [1/4] 큐레이션 매니저 - 음악 선정 중...")
    cur = curate_music(mood)
    print(cur)
    m = parse_curation(cur)
    if not m["artist"]:
        m["artist"] = input("아티스트 이름: ").strip()
        m["album"]  = input("앨범 이름: ").strip()
        m["track"]  = input("트랙 이름: ").strip()
    print(f"\n📖 [2/4] 음악정보 매니저 - {m['artist']} 정보 수집 중...")
    info = get_music_info(m["artist"], m["album"], m["track"])
    print(f"\n🔊 [3/4] 오디오 매니저 - 청취 가이드 작성 중...")
    audio = get_audio_info(m["artist"], m["album"], m["track"])
    print(f"\n✍️  [4/4] 총괄 매니저 - 블로그 글 작성 중...")
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    prompt = f"""당신은 감성적인 음악 블로그 작가입니다.
오늘의 테마: {mood}
추천 음악: {m['artist']} - {m['track']} ({m['album']})
[큐레이션 이유] {cur}
[음악 배경 정보] {info}
[오디오 청취 가이드] {audio}
700~900자 에세이 스타일로, 소제목 없이 자연스럽게 써주세요.
마지막은 독자에게 지금 이 음악을 틀어보라는 권유로 마무리해주세요."""
    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    post = msg.content[0].text
    fname = f"blog_{m['artist'].replace(' ', '_')}.txt"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(f"[테마: {mood}]\n[음악: {m['artist']} - {m['track']}]\n\n{post}")
    print(f"\n✅ 완성! {fname} 저장됨")
    return post

if __name__ == "__main__":
    print("=" * 50)
    print("  🎼 음악 블로그 에이전트")
    print("=" * 50)
    mood = input("\n오늘의 분위기나 키워드: ").strip()
    if not mood:
        mood = "늦은 밤 혼자 걷는 고요한 느낌"
    post = write_blog_post(mood)
    print("\n" + "=" * 50)
    print("📝 완성된 블로그 글")
    print("=" * 50)
    print(post)
