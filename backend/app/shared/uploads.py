"""표로 올리는 본문 받기 — 첨부(`files`)와 STEP(`works`)의 두 문이 같은 규칙으로 받는다.

올리는 요청에는 토큰이 없고 표가 곧 자격이다(ADR 0012). 그래서 **표를 먼저 본 뒤에** 이것을
부른다. 밝힌 크기(`Content-Length`)가 상한을 넘으면 받기 전에 끊고, 안 밝힌 본문은 흘려 받으며
세다가 상한을 넘는 순간 끊는다 — 다 받고 나서 재지 않는다.
"""

from __future__ import annotations

import tempfile
from typing import Any

from starlette.requests import Request

from app.shared.errors import AppError, code


def too_large(limit: int) -> AppError:
    return AppError(
        code("FILES", 3),
        f"파일이 너무 큽니다 (최대 {limit // 1024 // 1024}MB).",
        status=413,
        details={"max_bytes": limit},
    )


async def spooled_body(request: Request, limit: int) -> Any:
    """본문을 임시 파일(1MB 까지는 메모리)에 받아 처음으로 감아 돌려준다 — 닫는 것은 부르는
    쪽이다(`with`)."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise too_large(limit)
    # 닫는 것은 부르는 쪽이다(돌려준 뒤 `with`) — 여기서 `with` 로 열면 돌려주기 전에 닫힌다.
    spool = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)  # noqa: SIM115
    size = 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                raise too_large(limit)
            spool.write(chunk)
    except BaseException:
        spool.close()
        raise
    spool.seek(0)
    return spool
