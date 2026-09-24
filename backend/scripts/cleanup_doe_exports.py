"""오래된 DOE 폴더를 치운다 — **파일만.** 스터디와 이력은 지우지 않는다.

    .venv/bin/python scripts/cleanup_doe_exports.py --dry-run   무엇이 지워질지만 본다
    .venv/bin/python scripts/cleanup_doe_exports.py             두 폴더 모두 치운다
    .venv/bin/python scripts/cleanup_doe_exports.py --only shared|local   한쪽만

폴더는 둘이고 뜻이 다르다:

- **공유 폴더**(해석이 읽는 곳)는 보관소가 아니라 **전달 큐**다. 「다 읽었다」 는 신호나 기한
  (기본 30일)이 오면 사본을 치운다 — 「보내기」 를 다시 누르면 같은 폴더가 다시 선다.
- **서버 보관 폴더**(filestore/doe/…)는 보관소이고 「보내기」 의 복사원이라 더 길게 둔다
  (기본 180일). 여기 파일이 없어져도 스냅샷(레시피 · 인자 · 시드 · 조건)이 DB 에 남으므로
  화면은 그대로 뜨고, **「다시 만들기」** 가 같은 파일을 되살린다.

둘 다 **영구보관**(스터디마다 켠다)이면 기한과 무관하게 남는다. 기한 0 은 자동 삭제 끄기다.

**순서가 있다.** 공유 폴더를 먼저 치워야 서버 보관 폴더가 차례를 얻는다 — 아직 해석에 나가
있는 스터디의 복사원을 먼저 지워 두면 「다시 보내 달라」 에 답할 길이 없어진다.

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


def _report(title: str, got: dict, dry_run: bool, empty: str) -> None:
    head = "지울 것" if dry_run else "치웠다"
    print(f"\n[{title}] {head}: {got['count']} 개")
    for one in got["removed"]:
        print(f"  {one['name']}  {one['folder']}")
    if got["count"] == 0:
        print(f"  (없음 — {empty})")


def main() -> int:
    parser = argparse.ArgumentParser(description="오래된 DOE 폴더를 치운다")
    parser.add_argument("--dry-run", action="store_true", help="지우지 않고 목록만")
    parser.add_argument(
        "--only",
        choices=("shared", "local"),
        help="한쪽만 — shared 는 공유 폴더, local 은 서버 보관 폴더",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        # 공유 폴더가 먼저다 — 그것이 비어야 서버 보관 폴더가 치울 대상이 된다.
        if args.only != "local":
            _report(
                "공유 폴더",
                services.cleanup_exports(db, dry_run=args.dry_run),
                args.dry_run,
                "영구보관이거나 기한 전이거나, 기한이 0 입니다",
            )
        if args.only != "shared":
            _report(
                "서버 보관 폴더",
                services.cleanup_locals(db, dry_run=args.dry_run),
                args.dry_run,
                "아직 공유 폴더에 나가 있거나, 영구보관이거나, 기한 전이거나 0 입니다",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
