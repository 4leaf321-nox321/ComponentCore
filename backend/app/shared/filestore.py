"""파일 저장소 — 올린 STEP 과 생성한 지그가 사는 곳.

DB 에는 **저장소 루트 기준 상대 경로**만 둔다. 절대 경로를 넣으면 filestore 를 옮기는
날(개발 PC → 서버) 모든 행이 깨진다.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from app.config import get_settings

_UNSAFE = re.compile(r"[^A-Za-z0-9._가-힣-]+")


def root() -> Path:
    return get_settings().filestore_dir


def safe_filename(name: str) -> str:
    """경로 구분자와 제어 문자를 지운 이름. 비면 `file`."""
    cleaned = _UNSAFE.sub("_", Path(name).name).strip("._") or "file"
    return cleaned[:120]


def resolve(relative: str) -> Path:
    """상대 경로를 절대 경로로. **저장소 밖으로 나가면 거절한다.**"""
    base = root().resolve()
    target = (base / relative).resolve()
    if base not in target.parents and target != base:
        raise ValueError(f"저장소 밖의 경로입니다: {relative}")
    return target


def new_dir(*parts: str) -> Path:
    """`<root>/<parts...>/<uuid>` 폴더를 만들고 돌려준다."""
    target = root().joinpath(*parts, uuid.uuid4().hex)
    target.mkdir(parents=True, exist_ok=False)
    return target


def relative_to_root(path: Path) -> str:
    return str(path.resolve().relative_to(root().resolve())).replace("\\", "/")


def save_stream(stream: BinaryIO, target: Path, *, limit_bytes: int) -> int:
    """스트림을 파일로. 상한을 넘으면 지우고 ValueError."""
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with target.open("wb") as out:
        while chunk := stream.read(1024 * 1024):
            written += len(chunk)
            if written > limit_bytes:
                out.close()
                target.unlink(missing_ok=True)
                raise ValueError("파일이 상한을 넘습니다")
            out.write(chunk)
    return written


def remove_dir(relative: str) -> None:
    with contextlib.suppress(ValueError):
        shutil.rmtree(resolve(relative), ignore_errors=True)
