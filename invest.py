#!/usr/bin/env python3
"""📈 투자 일지 CLI.

사용법:
  python invest.py                          # 메모를 인터랙티브로 입력
  python invest.py --memo "오늘 엔비디아 일부 익절..."
  python invest.py --memo-file memo.txt
  python invest.py --no-publish             # Notion 발행 없이 로컬 저장만
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modes.investment.pipeline import run


def main():
    p = argparse.ArgumentParser(description="투자 일지 에이전트")
    p.add_argument("--memo", default="", help="오늘의 투자 메모")
    p.add_argument("--memo-file", default="", help="메모가 담긴 텍스트 파일 경로")
    p.add_argument("--no-publish", action="store_true", help="Notion 발행 생략")
    args = p.parse_args()

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
