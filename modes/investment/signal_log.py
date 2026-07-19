"""신호 이력 로그 — '신호의 성적표'.

퀀트의 철칙: 신호를 믿기 전에 신호의 성적표를 만들어라.
매 실행(브리핑/일지)마다 심볼별 신호 판정과 종가를 JSONL로 축적하고,
나중에 '신호 발생 후 5/20거래일 수익률'로 각 신호의 실제 성과를 검증한다.

- 파일: signal_log/YYYY-MM.jsonl (한 달에 하나, 한 줄 = 하루 스냅숏)
- 같은 날짜에 두 번 실행(브리핑+일지)하면 마지막 것으로 덮어씀
- git 커밋 대상 (개인 repo) — Actions 실행분도 워크플로우가 커밋해 누적
- 검증: `python invest.py --signal-report`
"""
import json
import os

from core import config
from modes.investment.signals import divergence, rebound, relative_strength, vcp

LOG_DIR = os.path.join(config.ROOT_DIR, "signal_log")

HORIZONS = (5, 20)  # 신호 발생 후 n거래일 수익률로 검증

# 리포트에서 집계할 신호 필드와 표시 이름
_TRACKED = {
    "divergence": "가격-거래량 다이버전스",
    "rebound": "반등 품질",
    "rs": "주도주 RS",
    "hs": "헤드앤숄더 의심",
    "vcp": "VCP 수축",
}


def snapshot(ctx) -> dict:
    """오늘의 심볼별 신호 판정을 구조화해서 뽑는다 (마크다운이 아닌 데이터로)."""
    dates = [rows[-1]["date"] for rows in ctx["histories"].values() if rows]
    entry = {"date": max(dates) if dates else "", "symbols": {}}
    for sym, rows in ctx["histories"].items():
        rec = {"close": rows[-1]["close"]}
        d = divergence.detect(rows)
        if d and d["signal"] != "none":
            rec["divergence"] = d["signal"]
        r = rebound.analyze(rows)
        if r:
            rec["rebound"] = r.get("verdict") or r["phase"]
            if r.get("hs"):
                rec["hs"] = "detected"
        v = vcp.detect(rows)
        if v:
            rec["vcp"] = "near_pivot" if v["near_pivot"] else "contracting"
        bench = ctx.get("benchmarks", {}).get(sym)
        if bench and bench in ctx["histories"]:
            rs = relative_strength.analyze(rows, ctx["histories"][bench])
            if "insufficient" not in rs:
                # 이모지 문구 대신 안정적인 코드로 저장
                if "이탈" in rs["verdict"]:
                    rec["rs"] = "exit_warning"
                elif "건재" in rs["verdict"]:
                    rec["rs"] = "strong"
                elif "약화" in rs["verdict"]:
                    rec["rs"] = "weakening"
                elif "개선" in rs["verdict"]:
                    rec["rs"] = "improving"
        entry["symbols"][sym] = rec
    return entry


def record(ctx):
    """오늘 스냅숏을 월별 JSONL에 기록 (같은 날짜는 덮어씀). 실패해도 조용히 넘어감."""
    try:
        entry = snapshot(ctx)
        if not entry["date"] or not entry["symbols"]:
            return None
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, f"{entry['date'][:7]}.jsonl")
        lines = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                lines = [ln for ln in f.read().splitlines() if ln.strip()]
        kept = [ln for ln in lines if json.loads(ln).get("date") != entry["date"]]
        kept.append(json.dumps(entry, ensure_ascii=False))
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(kept) + "\n")
        return path
    except Exception as e:
        print(f"  ⚠️ 신호 로그 기록 실패: {e}")
        return None


def load_entries():
    """모든 월 파일의 스냅숏을 날짜순으로 로드."""
    if not os.path.isdir(LOG_DIR):
        return []
    entries = []
    for fname in sorted(os.listdir(LOG_DIR)):
        if not fname.endswith(".jsonl"):
            continue
        with open(os.path.join(LOG_DIR, fname), encoding="utf-8") as f:
            for ln in f.read().splitlines():
                if ln.strip():
                    try:
                        entries.append(json.loads(ln))
                    except json.JSONDecodeError:
                        continue
    entries.sort(key=lambda e: e.get("date", ""))
    return entries


def performance_report(ctx) -> str:
    """신호별 사후 성과 리포트 — 발생 후 5/20거래일 수익률 집계.

    미래 가격은 현재 ctx의 히스토리에서 찾는다 (거래일 인덱스 기준).
    """
    entries = load_entries()
    lines = ["### 📋 신호 성적표 (발생 후 거래일 수익률)"]
    if not entries:
        lines.append("- 아직 기록된 신호 로그가 없다. 매일 실행이 쌓이면 자동으로 채워진다.")
        return "\n".join(lines)

    # 심볼별 거래일 인덱스: date → (idx, closes 리스트)
    index = {}
    for sym, rows in ctx["histories"].items():
        dates = [r["date"] for r in rows]
        closes = [r["close"] for r in rows]
        index[sym] = ({d: i for i, d in enumerate(dates)}, closes)

    # stats[신호필드][신호값][horizon] = [수익률들]
    stats = {}
    for e in entries:
        for sym, rec in e.get("symbols", {}).items():
            if sym not in index:
                continue
            date_idx, closes = index[sym]
            i = date_idx.get(e["date"])
            if i is None:
                continue
            for field in _TRACKED:
                val = rec.get(field)
                if not val:
                    continue
                for h in HORIZONS:
                    if i + h < len(closes) and closes[i]:
                        ret = (closes[i + h] / closes[i] - 1) * 100
                        stats.setdefault(field, {}).setdefault(val, {}).setdefault(h, []).append(ret)

    if not stats:
        n = len(entries)
        lines.append(f"- 로그 {n}일치 축적 중 — 신호 발생 후 {HORIZONS[0]}거래일이 지나면 성과가 집계된다.")
        return "\n".join(lines)

    lines.append("| 신호 | 판정 | 건수 | +5일 평균 | +20일 평균 |")
    lines.append("| --- | --- | ---: | ---: | ---: |")
    for field, by_val in stats.items():
        for val, by_h in sorted(by_val.items()):
            r5 = by_h.get(5, [])
            r20 = by_h.get(20, [])
            n = max(len(r5), len(r20))
            avg5 = f"{sum(r5)/len(r5):+.2f}%" if r5 else "—"
            avg20 = f"{sum(r20)/len(r20):+.2f}%" if r20 else "—"
            lines.append(f"| {_TRACKED[field]} | {val} | {n} | {avg5} | {avg20} |")
    lines.append("")
    lines.append("해석 가이드: 약세 신호(bearish_divergence, exit_warning) 뒤 수익률이 실제로"
                 " 나빴다면 신호가 유효하다는 뜻. 건수가 10건 미만이면 참고만 할 것.")
    return "\n".join(lines)
