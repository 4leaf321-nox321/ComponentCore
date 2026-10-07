"""물성 사전 — 못 닿으면 마지막으로 받은 사본으로 표준 열쇠를 붙인다.

MatNexus 가 꺼진 날 재생성한 스터디가 열쇠 없이 나가, 해석 쪽(SimEngBay)이 「물성을 읽지
못했습니다」 로 거절했다(2026-10-05). 재생성 결과가 그날 MatNexus 가 떠 있는지에 따라 달라지면
안 된다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.shared.clients import matnexus

DICTIONARY = {
    "properties": [
        {
            "key": "mechanical.youngs_modulus",
            "name": "Young's modulus",
            "internal_items": ["탄성계수"],
            "aliases": ["영률"],
        }
    ]
}


def test_못_닿으면_마지막으로_받은_사전으로_열쇠를_붙인다(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(matnexus, "_dictionary_file", lambda: tmp_path / "dictionary.json")
    monkeypatch.setattr(matnexus, "_DICTIONARY", None)
    monkeypatch.setattr(matnexus, "_get", lambda path, params=None: DICTIONARY)
    assert matnexus.property_keys()["탄성계수"] == "mechanical.youngs_modulus"

    def down(path: str, params: dict[str, Any] | None = None) -> Any:
        raise matnexus.MatNexusUnavailable("MatNexus에 연결하지 못했습니다")

    # 새 프로세스(워커)처럼 — 기억한 것은 없고 그쪽은 꺼져 있다.
    monkeypatch.setattr(matnexus, "_DICTIONARY", None)
    monkeypatch.setattr(matnexus, "_get", down)
    assert matnexus.property_keys()["영률"] == "mechanical.youngs_modulus"

    # 사본도 없으면 빈 표 — 열쇠를 안 붙일 뿐 물성은 나간다(그때는 설계점에 경고가 남는다).
    (tmp_path / "dictionary.json").unlink()
    assert matnexus.property_keys() == {}
