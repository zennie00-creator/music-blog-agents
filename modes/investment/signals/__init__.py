"""시장 신호 레지스트리.

'봐야 되는 조건'이 생길 때마다 이 패키지에 모듈 하나를 추가하고
ALL 리스트에 등록하면 일지 파이프라인에 자동 반영된다.

각 신호 모듈의 인터페이스:
  TITLE: str                — 섹션 제목
  run(ctx) -> str | None    — 마크다운 섹션 반환. 해당 없음이면 None.

ctx(dict) 구성 (market_data.collect_context() 참조):
  ctx["histories"]  : {심볼: [{date, close, volume}, ...]}  과거→최신 순
  ctx["names"]      : {심볼: 표시 이름}
  ctx["fear_greed"] : {"score", "rating"} | None
"""
from modes.investment.signals import (
    divergence, rebound, put_call, yield_curve, relative_strength,
)

ALL = [yield_curve, divergence, rebound, relative_strength, put_call]


def run_all(ctx) -> str:
    sections = []
    for mod in ALL:
        try:
            md = mod.run(ctx)
        except Exception as e:
            md = f"### {mod.TITLE}\n- ⚠️ 신호 계산 실패: {e}"
        if md:
            sections.append(md)
    return "\n\n".join(sections)
