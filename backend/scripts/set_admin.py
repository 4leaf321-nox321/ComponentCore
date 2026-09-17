"""관리자 계정을 만들거나 고친다 — 서버 콘솔에서 쓰는 복구 도구.

python scripts/set_admin.py --email admin --password '...'
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

import app.all_models  # noqa: F401
from app.database import SessionLocal
from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.auth.models import RefreshToken


def main() -> int:
    parser = argparse.ArgumentParser(description="관리자 계정 복구 도구")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--display-name", default="시스템 관리자")
    parser.add_argument("--force-change", action="store_true")
    args = parser.parse_args()

    email = args.email.strip().lower()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                password_hash=security.hash_password(args.password),
                display_name=args.display_name,
                status="active",
                is_system_admin=True,
            )
            db.add(user)
            db.flush()
            print(f"관리자 생성: {email}")
        else:
            user.password_hash = security.hash_password(args.password)
            print(f"비밀번호 변경: {email}")

        user.is_system_admin = True
        user.status = "active"
        user.deleted_at = None
        user.failed_logins = 0
        user.last_failed_login_at = None
        user.must_change_password = args.force_change

        revoked = 0
        for token in db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
            )
        ):
            token.revoked_at = datetime.now(UTC)
            revoked += 1
        db.commit()
        if revoked:
            print(f"  끊은 세션: {revoked}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
