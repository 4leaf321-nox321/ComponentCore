"""첫 설치 — 시스템 관리자 계정 하나.

**이것 없이는 아무도 로그인할 수 없다.** 가입 화면이 없고 계정은 관리자가 만든다.
**멱등하다** — 두 번 돌려도 이미 있는 관리자의 비밀번호를 되돌리지 않는다.

    python scripts/seed_install.py --email admin --name 관리자 [--password ...]

비밀번호를 안 주면 난수로 만들어 화면에 한 번만 찍는다. 첫 로그인에서 반드시 바꾸게 한다.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

import app.all_models  # noqa: F401
from app.config import get_settings
from app.database import SessionLocal
from app.modules.accounts.models import User
from app.modules.auth import security


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{get_settings().app_name} 첫 설치 시드")
    parser.add_argument("--email", default="admin")
    parser.add_argument("--name", default="시스템 관리자")
    parser.add_argument("--password", default=None)
    parser.add_argument(
        "--no-force-change",
        action="store_true",
        help="첫 로그인 비밀번호 변경을 강제하지 않는다(개발 PC 용)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        email = args.email.strip().lower()
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            if not user.is_system_admin:
                user.is_system_admin = True
                print(f"기존 계정에 시스템 관리자 권한 부여: {email}")
            db.commit()
            print(f"이미 있는 계정입니다: {email} (비밀번호는 그대로)")
            return 0

        password = args.password or secrets.token_urlsafe(9)
        db.add(
            User(
                email=email,
                password_hash=security.hash_password(password),
                display_name=args.name,
                status="active",
                is_system_admin=True,
                must_change_password=not args.no_force_change,
            )
        )
        db.commit()
        print(f"관리자 계정 생성: {email}")
        print(f"임시 비밀번호: {password}")
        if not args.no_force_change:
            print("첫 로그인에서 비밀번호를 바꿔야 합니다.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
