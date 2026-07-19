"""푸시 알림 — ntfy.sh (무료, 가입·키 불필요).

'quiet unless signal' 패턴: 매일 알림이 오면 무시하게 되므로,
🚨급 신호가 뜬 날만 폰으로 한 줄 보낸다.

설정 (선택):
1. 폰에 ntfy 앱 설치 (iOS/Android) → 구독 토픽 이름 정하기
   (토픽 이름이 곧 비밀번호이므로 추측 불가능하게: 예 invest-zn-8k2p9x)
2. .env에 NTFY_TOPIC=토픽이름
미설정이면 알림 기능은 조용히 꺼져 있다.
"""
import os

import requests


def push(message: str, title: str = "Invest Signal", click_url: str = "") -> bool:
    """NTFY_TOPIC이 설정돼 있으면 푸시 발송. 실패해도 파이프라인은 계속."""
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        return False
    try:
        headers = {"Title": title.encode("ascii", "ignore").decode() or "Invest"}
        if click_url:
            headers["Click"] = click_url
        r = requests.post(f"https://ntfy.sh/{topic}",
                          data=message.encode("utf-8"), headers=headers, timeout=15)
        r.raise_for_status()
        print(f"  📱 푸시 알림 전송 (ntfy/{topic[:6]}…)")
        return True
    except Exception as e:
        print(f"  ⚠️ 푸시 알림 실패: {e}")
        return False


def alert_lines(signals_md: str, max_lines: int = 5):
    """신호 마크다운에서 🚨(경보)·✳️(바닥 신호) 라인만 추출."""
    hits = []
    for line in signals_md.splitlines():
        s = line.strip()
        if s.startswith("-") and ("🚨" in s or "✳️" in s):
            hits.append(s.lstrip("- ").strip())
    return hits[:max_lines]
