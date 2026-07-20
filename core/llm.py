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


_XAI_BASE = "https://api.x.ai/v1"

# 프로세스 내에서 한 번 해결한 모델명을 재사용 (매 호출 /v1/models 조회 방지).
_RESOLVED_GROK_MODEL = None


def _pick_grok_model(model_ids) -> str:
    """xAI /v1/models 목록에서 채팅용 flagship Grok 모델을 고른다.

    은퇴(410)·오타(404)로 설정 모델을 못 쓸 때, 이 키로 실제 사용 가능한
    모델 중 가장 적합한 것을 자동 선택한다. 이미지·미니·코드 전용은 제외하고
    grok-4 계열을 우선한다.
    """
    ids = [m for m in model_ids if isinstance(m, str) and m.startswith("grok")]
    bad = ("image", "vision", "mini", "code", "embed")
    chat = [m for m in ids if not any(b in m for b in bad)]
    if not chat:
        raise RuntimeError("xAI /v1/models에 사용 가능한 grok 모델이 없습니다")

    def tiers(m: str):
        # 낮을수록 선호: grok-4 계열 > 정식(fast 아님) > reasoning > -latest 별칭
        return (
            0 if m.startswith("grok-4") else 1,
            1 if "fast" in m else 0,
            1 if "non-reasoning" in m else 0,
            0 if m.endswith("latest") else 1,
        )

    # 안정 정렬 2단계: 먼저 이름 내림차순(같은 등급 내 최신 스냅숏 우선),
    # 그 위에 등급 오름차순 → 등급이 같으면 최신 스냅숏이 앞선다.
    chat.sort(reverse=True)
    chat.sort(key=tiers)
    return chat[0]


def _resolve_grok_model() -> str:
    """/v1/models를 조회해 현재 사용 가능한 Grok 모델명을 반환 (실패 시 예외)."""
    r = requests.get(
        f"{_XAI_BASE}/models",
        headers={"Authorization": f"Bearer {config.XAI_API_KEY}"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json().get("data", [])
    return _pick_grok_model([m.get("id", "") for m in data])


def ask_grok(system: str, user: str, live_search: bool = True,
             max_tokens: int = 4096, timeout: int = 300,
             x_handles=None) -> str:
    """Grok(xAI)에게 단발 요청.

    live_search=True면 xAI 라이브 검색을 켜서 최신 뉴스·X 게시물을
    참고한 분석을 받는다 (시장/테크 브리핑에 필요).
    x_handles를 주면 해당 X 계정들의 발언을 검색 대상에 명시적으로 포함한다.
    검색 파라미터 스키마가 거절되면(4xx) 기본 검색으로 자동 폴백.
    설정 모델이 은퇴(410)·부재(404)면 /v1/models로 사용 가능한 모델을 찾아 재시도.
    """
    if not config.XAI_API_KEY:
        raise RuntimeError("XAI_API_KEY가 설정되지 않았습니다 (.env 확인)")

    def _post(model, search_params):
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
        }
        if search_params:
            payload["search_parameters"] = search_params
        r = requests.post(
            f"{_XAI_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.XAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def _call(search_params):
        """설정 모델로 호출하되, 모델 은퇴/부재(410·404)면 자동 교체 후 재시도."""
        global _RESOLVED_GROK_MODEL
        model = _RESOLVED_GROK_MODEL or config.GROK_MODEL
        try:
            return _post(model, search_params)
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else None
            if code in (404, 410) and _RESOLVED_GROK_MODEL is None:
                new_model = _resolve_grok_model()  # /v1/models 실패하면 예외 전파
                print(f"  ⚠️ Grok 모델 '{model}' 사용 불가({code}) → '{new_model}'로 자동 교체")
                _RESOLVED_GROK_MODEL = new_model
                return _post(new_model, search_params)
            raise

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
