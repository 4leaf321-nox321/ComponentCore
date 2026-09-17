"""OpenAPI 스키마를 파일로 뽑는다 — 프론트 타입의 원본이다.

python scripts/export_openapi.py
cd ../frontend && npm run api:types
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import version
from app.main import app

OUT = Path(__file__).resolve().parents[1] / "openapi.json"


def main() -> int:
    schema = version.as_baseline(app.openapi())
    OUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{OUT} 에 썼습니다 ({len(schema.get('paths', {}))} 경로).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
