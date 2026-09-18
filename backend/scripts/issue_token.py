"""서버 콘솔에서 개인 토큰을 발급한다 — 화면에 못 들어가는 자리(스크립트 · 배치)용.

    python scripts/issue_token.py --email admin --name "배치" --scopes read,write [--days 30]

평문은 이 출력에서 한 번만 나온다. 화면의 「내 정보」 에서도 같은 토큰을 보고 폐기할 수 있다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

import app.all_models  # noqa: F401
from app.database import SessionLocal
from app.modules.accounts.models import User
from app.modules.auth import services


def main() -> int:
    parser = argparse.ArgumentParser(description="개인 토큰 발급")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True, help="어디에 쓰는 토큰인지")
    parser.add_argument("--scopes", default="read", help="쉼표로: read,write")
    parser.add_argument("--days", type=int, default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
        if user is None:
            sys.exit(f"계정이 없습니다: {args.email}")
        scopes = [one.strip() for one in args.scopes.split(",") if one.strip()]
        raw, pat = services.create_pat(db, user, args.name, args.days, scopes)
        print(f"토큰({pat.name}, {', '.join(pat.scopes)}): {raw}")
        print("이 출력에서 한 번만 보입니다.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
