import requests

def _itunes_artwork(query, entity="album"):
    """iTunes API 검색 후 첫 번째 결과의 600x600 이미지 URL 반환"""
    try:
        q = requests.utils.quote(query)
        resp = requests.get(
            f"https://itunes.apple.com/search?term={q}&entity={entity}&limit=3",
            timeout=5
        )
        data = resp.json()
        if data.get("resultCount", 0) > 0:
            url = data["results"][0].get("artworkUrl100", "")
            if url:
                return url.replace("100x100bb", "600x600bb")
    except Exception:
        pass
    return None


def get_album_art(artist, album, track=""):
    """
    앨범 아트 URL 반환. 여러 전략으로 순차 시도:
    1. artist + album
    2. artist + track (album 검색 실패 시)
    3. artist만
    """
    # 전략 1: 아티스트 + 앨범명 (앨범명이 너무 길거나 특수한 경우 앞 30자만)
    if album:
        short_album = album[:40]  # 너무 긴 버전명은 검색 방해
        url = _itunes_artwork(f"{artist} {short_album}")
        if url:
            return url

    # 전략 2: 아티스트 + 트랙명
    if track:
        url = _itunes_artwork(f"{artist} {track}")
        if url:
            return url

    # 전략 3: 아티스트만
    url = _itunes_artwork(artist)
    return url


def get_artist_image(artist):
    """Deezer API로 아티스트 이미지 URL 반환 (무료, 무인증)"""
    try:
        query = requests.utils.quote(artist)
        resp = requests.get(
            f"https://api.deezer.com/search/artist?q={query}&limit=1",
            timeout=5
        )
        data = resp.json()
        items = data.get("data", [])
        if items:
            return items[0].get("picture_medium") or items[0].get("picture")
    except Exception:
        pass
    return None
