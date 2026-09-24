"""공유 폴더의 오래된 스터디 폴더를 치운다 — **사본만.**

    .venv/bin/python scripts/cleanup_doe_exports.py --dry-run   무엇이 지워질지만 본다
    .venv/bin/python scripts/cleanup_doe_exports.py             실제로 치운다

공유 폴더는 보관소가 아니라 **전달 큐**다. 정본은 서버 보관 폴더와 DB 이고, 「보내기」 를 다시
누르면 같은 폴더가 다시 선다 — 그래서 이것은 파괴적인 일이 아니다.

지우는 대상은 **영구보관이 아니고**, 해석이 「다 읽었다」 고 알렸거나 보관 기한이 지난 것이다.
기한은 관리자가 화면에서 바꾼다(서버 > 설정, 기본 30일). 0 이면 자동 삭제를 안 한다.

운영에서는 systemd 타이머로 하루 한 번 돌린다 — 백업 타이머와 같은 방식.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.all_models  # noqa: F401
from app.database import SessionLocal
from app.modules.doe import services


def main() -> int:
    parser = argparse.ArgumentParser(description="공유 폴더의 오래된 DOE 폴더를 치운다")
    parser.add_argument("--dry-run", action="store_true", help="지우지 않고 목록만")
    args = parser.parse_args()

    with SessionLocal() as db:
        got = services.cleanup_exports(db, dry_run=args.dry_run)

    head = "지울 것" if args.dry_run else "치웠다"
    print(f"{head}: {got['count']} 개")
    for one in got["removed"]:
        print(f"  {one['name']}  {one['folder']}")
    if got["count"] == 0:
        print("  (없음 — 영구보관이거나 기한 전이거나, 기한이 0 입니다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
