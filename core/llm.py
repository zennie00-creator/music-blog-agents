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


def _rank_grok_models(model_ids):
    """xAI /v1/models 목록을 채팅용 Grok 우선순위로 정렬한 리스트로 반환.

    은퇴(410)·오타(404)로 설정 모델을 못 쓸 때, 이 키로 실제 존재하는
    모델을 우선순위대로 하나씩 시도하기 위한 후보 목록. 이미지·미니·코드
    전용은 제외하고 grok-4 계열·정식·reasoning·최신 스냅숏을 우선한다.
    """
    ids = [m for m in model_ids if isinstance(m, str) and m.startswith("grok")]
    bad = ("image", "vision", "mini", "code", "embed")
    chat = [m for m in ids if not any(b in m for b in bad)]

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
    return chat


def _pick_grok_model(model_ids) -> str:
    """우선순위 1위 Grok 모델 (후보가 없으면 예외)."""
    ranked = _rank_grok_models(model_ids)
    if not ranked:
        raise RuntimeError("xAI /v1/models에 사용 가능한 grok 모델이 없습니다")
    return ranked[0]


def _grok_candidates():
    """/v1/models를 조회해 우선순위 정렬된 Grok 모델 후보 리스트 반환."""
    r = requests.get(
        f"{_XAI_BASE}/models",
        headers={"Authorization": f"Bearer {config.XAI_API_KEY}"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json().get("data", [])
    return _rank_grok_models([m.get("id", "") for m in data])


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

    def _headers():
        return {"Authorization": f"Bearer {config.XAI_API_KEY}",
                "Content-Type": "application/json"}

    def _post_chat(model, search_params):
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
        r = requests.post(f"{_XAI_BASE}/chat/completions",
                          headers=_headers(), json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def _post_responses(model, search_params):
        """신형 Responses API. chat/completions가 410(엔드포인트 은퇴)일 때 시도."""
        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_output_tokens": max_tokens,
        }
        if search_params:
            payload["search_parameters"] = search_params
        r = requests.post(f"{_XAI_BASE}/responses",
                          headers=_headers(), json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        txt = data.get("output_text")
        if not txt:  # output 배열에서 텍스트 수집 (형태 방어)
            parts = []
            for item in data.get("output", []) or []:
                for c in (item.get("content") or []) if isinstance(item, dict) else []:
                    if isinstance(c, dict) and c.get("text"):
                        parts.append(c["text"])
            txt = "".join(parts)
        if not txt:
            raise ValueError("xAI /responses 응답에서 텍스트를 찾지 못함")
        return txt.strip()

    def _post(model, search_params):
        try:
            return _post_chat(model, search_params)
        except requests.HTTPError as e:
            # chat/completions가 410(Gone)이면 엔드포인트 은퇴 가능성 → responses 시도
            if e.response is not None and e.response.status_code == 410:
                return _post_responses(model, search_params)
            raise

    _GONE = (404, 410, 422)  # 모델 부재/은퇴/미지원 → 다음 후보 시도

    def _call(search_params):
        """설정 모델로 호출하되, 모델이 안 되면 /v1/models 후보를 순서대로 시도.

        grok-4-latest도 grok-4.5도 410을 주는 상황을 겪어, 한 후보에서 멈추지
        않고 실제로 200이 나오는 모델을 찾을 때까지 순회한다. 성공 모델은 캐시."""
        global _RESOLVED_GROK_MODEL
        if _RESOLVED_GROK_MODEL:
            return _post(_RESOLVED_GROK_MODEL, search_params)

        # 1) 설정 모델 먼저
        try:
            return _post(config.GROK_MODEL, search_params)
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else None
            if code not in _GONE:
                raise  # 인증·레이트리밋 등은 후보 순회로 안 풀림

        # 2) /v1/models 후보를 우선순위대로 순회하며 처음 성공하는 모델 채택
        candidates = _grok_candidates()
        print(f"  🔎 xAI 사용 가능 Grok 후보: {candidates}")
        last = None
        for m in candidates:
            if m == config.GROK_MODEL:
                continue
            try:
                out = _post(m, search_params)
                _RESOLVED_GROK_MODEL = m
                print(f"  ✅ Grok 모델 자동 교체 → '{m}'")
                return out
            except requests.HTTPError as e:
                last = e
                code = e.response.status_code if e.response is not None else None
                if code in _GONE:
                    continue
                raise  # 모델 문제가 아닌 오류는 즉시 전파
        raise last or RuntimeError("xAI에서 사용 가능한 Grok 모델을 찾지 못했습니다")

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


def grok_diagnose():
    """xAI 원인 진단 — /v1/models · chat/completions · responses 각각의 원응답을 찍는다.

    Grok가 왜 안 되는지(엔드포인트 은퇴? 모델? 권한?) Actions 로그로 확인하기 위함.
    `python invest.py --check`에서 호출.
    """
    if not config.XAI_API_KEY:
        print("  ❌ XAI_API_KEY 없음"); return
    h = {"Authorization": f"Bearer {config.XAI_API_KEY}", "Content-Type": "application/json"}
    # 1) 모델 목록
    try:
        r = requests.get(f"{_XAI_BASE}/models", headers=h, timeout=20)
        ids = [m.get("id") for m in r.json().get("data", [])] if r.ok else []
        print(f"  · GET /models → {r.status_code} · 모델 {len(ids)}개: {ids[:6]}")
    except Exception as e:
        print(f"  · GET /models 실패: {e}")
        ids = []
    model = (_rank_grok_models(ids) or ["grok-4"])[0]
    body = {"model": model, "max_tokens": 8}
    # 2) chat/completions
    try:
        r = requests.post(f"{_XAI_BASE}/chat/completions", headers=h, timeout=30,
                          json={**body, "messages": [{"role": "user", "content": "ping"}]})
        print(f"  · POST /chat/completions ({model}) → {r.status_code} · {r.text[:160]}")
    except Exception as e:
        print(f"  · POST /chat/completions 실패: {e}")
    # 3) responses (신형 API)
    try:
        r = requests.post(f"{_XAI_BASE}/responses", headers=h, timeout=30,
                          json={"model": model, "input": "ping", "max_output_tokens": 8})
        print(f"  · POST /responses ({model}) → {r.status_code} · {r.text[:160]}")
    except Exception as e:
        print(f"  · POST /responses 실패: {e}")
