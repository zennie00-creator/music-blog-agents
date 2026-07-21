"""공통 설정 모듈 — .env 로드 + 환경변수 접근.

리포 루트에 .env 파일을 두면 자동으로 읽는다 (.env.example 참고).
이미 설정된 환경변수는 덮어쓰지 않는다.
"""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_dotenv():
    path = os.path.join(_ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

ROOT_DIR = _ROOT

# LLM
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
# grok-4는 스냅숏이 은퇴하면 410 Gone을 준다. -latest 별칭은 항상 최신
# grok-4 스냅숏을 가리켜 은퇴에 안전하다. (은퇴 시 llm.py가 /v1/models로 자동 복구)
GROK_MODEL = os.environ.get("GROK_MODEL", "grok-4-latest")

# 시장 데이터 — 구글시트 웹 게시 CSV URL(들). 쉼표로 여러 개. (Yahoo 429 우회)
MARKET_CSV_URLS = os.environ.get("MARKET_CSV_URLS", "")

# Notion
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
NOTION_VERSION = os.environ.get("NOTION_VERSION", "2022-06-28")
