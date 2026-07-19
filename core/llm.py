"""공통 LLM 클라이언트 — Claude(Anthropic) + Grok(xAI).

- Claude: 일지 작성 등 최종 글쓰기 담당. anthropic SDK 사용.
- Grok: 시장·테크 분석 담당. xAI API(라이브 검색 지원)를 requests로 직접 호출.
"""
import requests
import anthropic

from core import config


def ask_claude(system: str, user: str, max_tokens: int = 16000) -> str:
    """Claude에게 단발 요청. 긴 출력을 대비해 스트리밍으로 받는다."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY or None)
    with client.messages.stream(
        model=config.CLAUDE_MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("Claude가 요청을 거절했습니다 (stop_reason=refusal)")
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def ask_grok(system: str, user: str, live_search: bool = True,
             max_tokens: int = 4096, timeout: int = 300,
             x_handles=None) -> str:
    """Grok(xAI)에게 단발 요청.

    live_search=True면 xAI 라이브 검색을 켜서 최신 뉴스·X 게시물을
    참고한 분석을 받는다 (시장/테크 브리핑에 필요).
    x_handles를 주면 해당 X 계정들의 발언을 검색 대상에 명시적으로 포함한다.
    검색 파라미터 스키마가 거절되면(4xx) 기본 검색으로 자동 폴백.
    """
    if not config.XAI_API_KEY:
        raise RuntimeError("XAI_API_KEY가 설정되지 않았습니다 (.env 확인)")

    def _call(search_params):
        payload = {
            "model": config.GROK_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
        }
        if search_params:
            payload["search_parameters"] = search_params
        r = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {config.XAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    if not live_search:
        return _call(None)

    if x_handles:
        rich = {
            "mode": "auto",
            "sources": [
                {"type": "web"},
                {"type": "news"},
                {"type": "x", "included_x_handles": list(x_handles)},
            ],
        }
        try:
            return _call(rich)
        except requests.HTTPError as e:
            if e.response is not None and 400 <= e.response.status_code < 500:
                print("  ⚠️ X 핸들 검색 파라미터 미지원 — 기본 검색으로 폴백")
            else:
                raise
    return _call({"mode": "auto"})
