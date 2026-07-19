#!/usr/bin/env python3
"""📈 투자 일지 CLI.

사용법:
  python invest.py --brief                  # 아침: 모닝 브리핑 (자동 실행용, 메모 없음)
  python invest.py                          # 오후: 투자 일지 (메모를 인터랙티브로 입력)
  python invest.py --memo "오늘 엔비디아 일부 익절..."
  python invest.py --memo-file memo.txt
  python invest.py --no-publish             # Notion 발행 없이 로컬 저장만
  python invest.py --ask "질문"             # Grok 단발 리서치 (insights.md 기록)
  python invest.py --discuss "주제"         # 나·Grok·Claude 삼자 토론 (이어하기 지원)
  python invest.py --discuss                # 최근 토론 이어서 재개
  python invest.py --check                  # 데이터 소스·API 연결 헬스체크
  python invest.py --signal-report          # 신호 성적표 (발생 후 5/20일 수익률)
  python invest.py --weekly                 # 주간 회고 (지난 7일 일지+신호 리뷰)
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modes.investment.pipeline import run, run_brief, load_thesis
from modes.investment import discussion


def main():
    p = argparse.ArgumentParser(description="투자 일지 에이전트")
    p.add_argument("--brief", action="store_true", help="아침 모닝 브리핑 실행")
    p.add_argument("--memo", default="", help="오늘의 투자 메모")
    p.add_argument("--memo-file", default="", help="메모가 담긴 텍스트 파일 경로")
    p.add_argument("--no-publish", action="store_true", help="Notion 발행 생략")
    p.add_argument("--ask", default="", help="Grok 단발 리서치 질문 (insights.md 기록)")
    p.add_argument("--discuss", nargs="?", const="__latest__", default="",
                   help="삼자 토론 주제 (생략 시 최근 토론 재개)")
    p.add_argument("--check", action="store_true", help="데이터 소스·API 연결 헬스체크")
    p.add_argument("--signal-report", action="store_true", help="신호 성적표 출력")
    p.add_argument("--weekly", action="store_true", help="주간 회고 생성·발행")
    args = p.parse_args()

    if args.check:
        from modes.investment.healthcheck import run_check
        run_check()
        return

    if args.weekly:
        from modes.investment.weekly import run_weekly
        run_weekly(publish=not args.no_publish)
        return

    if args.signal_report:
        from modes.investment import market_data, signal_log
        print("📊 시세 수집 중 (수익률 계산용)...")
        ctx = market_data.collect_context()
        print()
        print(signal_log.performance_report(ctx))
        return

    if args.brief:
        run_brief(publish=not args.no_publish)
        return

    if args.ask:
        print(discussion.ask_once(args.ask, thesis=load_thesis()))
        return
    if args.discuss:
        topic = args.discuss
        if topic == "__latest__":
            topic = discussion.latest_topic()
            if not topic:
                print("재개할 토론이 없습니다. --discuss \"주제\" 로 새로 시작하세요.")
                return
        discussion.discuss(topic, thesis=load_thesis())
        return

    memo = args.memo
    if args.memo_file:
        with open(args.memo_file, encoding="utf-8") as f:
            memo = f.read()
    elif not memo and sys.stdin.isatty():
        print("오늘의 투자 메모를 입력하세요 (빈 줄 두 번으로 종료):")
        lines = []
        empty = 0
        for line in sys.stdin:
            if line.strip() == "":
                empty += 1
                if empty >= 2:
                    break
            else:
                empty = 0
            lines.append(line)
        memo = "".join(lines).strip()

    result = run(memo=memo, publish=not args.no_publish)
    print("\n" + "=" * 60)
    print(result["journal"])


if __name__ == "__main__":
    main()
