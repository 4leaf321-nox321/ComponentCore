"""`server.py` 는 패키지가 아니라 **한 파일**이다 — 시험도 그 파일을 그대로 집어 오도록 폴더를
길에 넣는다."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _no_public_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """화면 주소를 백엔드에 묻지 않는다 — 「방금 물었고 없다」 로 둔다(이 기계에 운영 서버가
    떠 있어도 시험이 그것을 부르지 않게). 링크를 보는 시험은 이것을 덮어쓴다."""
    import server

    monkeypatch.setattr(server, "_PUBLIC_URL", "")
    monkeypatch.setattr(server, "_public_seen", (time.monotonic(), ""))
