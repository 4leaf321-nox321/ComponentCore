"""`scripts/compare_doe_points.py` — 옛 폴더와 다시 낸 폴더에서 바뀐 설계점 · 영역을 낸다."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[3] / "fixtures" / "simengbay" / "조건_볼트예압_판본딩"


def _script() -> Any:
    path = Path(__file__).resolve().parents[2] / "scripts" / "compare_doe_points.py"
    spec = importlib.util.spec_from_file_location("compare_doe_points_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_바뀐_영역만_낸다_판마다_다른_칸은_안_본다(tmp_path: Path) -> None:
    old, new = tmp_path / "old", tmp_path / "new"
    shutil.copytree(FIXTURE, old)
    shutil.copytree(FIXTURE, new)
    compare = _script().compare
    point = new / "points" / "p0001.json"
    body = json.loads(point.read_text(encoding="utf-8"))
    body["compcore_version"] = "v0.31.1"  # 판마다 다른 칸 — 안 본다
    point.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    assert compare(old, new) == []
    # v0.31.0 이 「위판 윗면」 을 고리 면으로 낸 꼴.
    body["regions"]["위판 윗면"] = [
        {
            "centroid": [0.0, 0.0, 18.0],
            "area": 82.74,
            "normal": [0.0, 0.0, 1.0],
            "body": "위판",
        }
    ]
    body["unresolved"] = ["볼트 머리"]
    point.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    assert compare(old, new) == [
        "p0001.json · 영역 ‘위판 윗면’",
        "p0001.json · 못 푼 것 [] → ['볼트 머리']",
    ]
