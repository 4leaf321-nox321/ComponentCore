"""DOE 폴더 둘의 점 파일을 견준다 — **어느 설계점의 어느 영역이 바뀌었나.** 읽기만 한다.

    .venv/bin/python scripts/compare_doe_points.py <옛 폴더> <새 폴더>

v0.31.0 은 중심이 구멍 속인 면을 가리키는 선택 그룹을 내보낼 때 옆의 딴 면으로 풀었다(v0.31.1
에서 고침). 그 버전으로 내보낸 폴더로 이미 해석했다면 **어느 결과가 틀린 면에 걸렸나**를 알아야
한다. 받는 쪽은 그것을 가릴 수 없다 — 영역의 지문(면의 무게중심 · 넓이 · 방향 · 바디)이 틀린
면의 것이어도 짝은 지어지기 때문이다. 그래서 고친 버전으로 다시 낸 폴더와 견준다.

1. 옛 폴더를 따로 둔다(해석 쪽이 받은 사본이면 된다) — 「재생성」 은 같은 폴더에 다시 쓴다.
2. 그 스터디를 v0.31.1 에서 「재생성」 한다.
3. 둘을 견준다. 영역(`regions`) · 바디(`bodies`) · 못 푼 것(`unresolved`)이 다른 설계점과 영역
   이름을 낸다. 같으면 아무것도 안 낸다.

`compcore_version` 처럼 판마다 다른 칸은 보지 않는다. 바뀐 것이 있으면 종료 코드 1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _points(folder: Path) -> dict[str, dict[str, Any]]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((folder / "points").glob("p*.json"))
    }


def compare(old: Path, new: Path) -> list[str]:
    """바뀐 것의 줄 — `p0003.json · 영역 ‘위판 윗면’` 꼴."""
    before, after = _points(old), _points(new)
    lines = [f"{name} · 새 폴더에 없음" for name in sorted(set(before) - set(after))]
    lines += [f"{name} · 옛 폴더에 없음" for name in sorted(set(after) - set(before))]
    for name in sorted(set(before) & set(after)):
        a, b = before[name], after[name]
        regions_a, regions_b = a.get("regions") or {}, b.get("regions") or {}
        for region in sorted(set(regions_a) | set(regions_b)):
            if regions_a.get(region) != regions_b.get(region):
                lines.append(f"{name} · 영역 ‘{region}’")
        if a.get("bodies") != b.get("bodies"):
            lines.append(f"{name} · 바디 목록")
        if sorted(a.get("unresolved") or []) != sorted(b.get("unresolved") or []):
            lines.append(
                f"{name} · 못 푼 것 {sorted(a.get('unresolved') or [])} → "
                f"{sorted(b.get('unresolved') or [])}"
            )
    return lines


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    old, new = Path(sys.argv[1]), Path(sys.argv[2])
    for folder in (old, new):
        if not (folder / "points").is_dir():
            print(f"{folder}: DOE 폴더가 아닙니다(points/ 가 없음).")
            return 2
    study = (
        json.loads((new / "study.json").read_text(encoding="utf-8"))
        if (new / "study.json").exists()
        else {}
    )
    lines = compare(old, new)
    label = f"스터디 ‘{study.get('name', '')}’ ({study.get('id', '')})"
    if not lines:
        print(f"{label}: 바뀐 영역이 없습니다.")
        return 0
    print(f"{label}: 바뀐 것 {len(lines)}개")
    for line in lines:
        print(f"  {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
