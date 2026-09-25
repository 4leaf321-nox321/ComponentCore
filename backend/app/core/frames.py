"""좌표계 — 원점과 세 축. 조건의 `cs`(구속의 성분 x · y · z 가 어느 방향인가)가 가리킨다.

두 곳에서 정의한다:

- **도면(레시피)** 의 `coordinate_systems` — 원점 · 회전을 치수 식(`"=길이/2"`)으로 적을 수
  있어 실험계획이 치수를 바꾸면 같이 움직인다.
- **해석 조건**의 `coordinate_systems` — 같은 모양(수치 · 식)이거나, **선택 그룹의 면에
  붙인다**(원점 = 면 중심, Z = 면의 법선). 면에 붙인 것은 설계점마다 그 면을 따라간다.

**계산은 여기 한 곳이다.** 화면은 서버가 푼 원점 · 축을 그리기만 한다 — 같은 회전을 화면이
따로 셈하면 두 벌이 어긋나는 날 3D 에 보인 방향과 내보낸 방향이 달라진다.

회전은 도면의 `transform` 과 같은 규칙: **X · Y · Z 축(고정된 전역 축) 순서로 돌린다**(도).
"""

from __future__ import annotations

import math
from typing import Any

Vec = tuple[float, float, float]


def _unit(v: Any) -> Vec:
    x, y, z = (float(one) for one in v)
    size = math.sqrt(x * x + y * y + z * z) or 1.0
    return (x / size, y / size, z / size)


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _rotate(v: Vec, rotate: Any) -> Vec:
    """X → Y → Z 축 순서로 돌린다(도, 고정 축)."""
    rx, ry, rz = (math.radians(float(one)) for one in rotate)
    x, y, z = v
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return (x, y, z)


def _row(name: str, source: str, origin: Any, x: Vec, y: Vec, z: Vec) -> dict[str, Any]:
    def r(v: Any) -> list[float]:
        return [round(float(one), 6) + 0.0 for one in v]

    return {
        "name": name,
        "source": source,
        "origin": r(origin),
        "x": r(x),
        "y": r(y),
        "z": r(z),
    }


def from_rotation(name: str, source: str, origin: Any, rotate: Any) -> dict[str, Any]:
    """원점 + 회전(X · Y · Z 순, 도)으로 정한 좌표계."""
    axes = [_rotate(one, rotate) for one in ((1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0))]
    return _row(name, source, origin, *axes)


def from_face(name: str, source: str, origin: Any, normal: Any) -> dict[str, Any]:
    """면에 붙인 좌표계 — 원점 = 면 중심, **Z = 법선.** X 는 전역 X 를 그 면에 눕힌 방향
    (법선이 X 와 나란하면 전역 Y) — 같은 면이면 늘 같은 X 가 나오게."""
    z = _unit(normal)
    helper: Vec = (1.0, 0.0, 0.0) if abs(z[0]) < 0.99 else (0.0, 1.0, 0.0)
    dot = sum(a * b for a, b in zip(helper, z, strict=True))
    x = _unit([h - dot * c for h, c in zip(helper, z, strict=True)])
    return _row(name, source, origin, x, _cross(z, x), z)


def recipe_frame_names(recipe: dict[str, Any]) -> list[str]:
    """도면(레시피)에 정한 좌표계 이름들 — 평가하지 않고 읽는다(조건 검증이 쓴다)."""
    rows = recipe.get("coordinate_systems") or []
    return [str(one.get("name")) for one in rows if isinstance(one, dict) and one.get("name")]


def condition_frames(
    frames: list[dict[str, Any]], regions: dict[str, list[dict[str, Any]]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """해석 조건의 좌표계(식이 풀린 것) → 원점 · 축. 그리고 **못 푼 이름들.**

    선택 그룹에 붙인 것은 그 그룹의 **첫 면**(`regions` — 이 설계점에서 푼 지문)에서 원점 ·
    법선을 얻는다. 원통면이면 축을 Z 로 쓴다. 그룹을 못 풀었으면 이 좌표계도 못 푼 것이다 —
    조용히 전역으로 바꾸면 성분이 딴 방향으로 걸린다.
    """
    out: list[dict[str, Any]] = []
    missing: list[str] = []
    for one in frames:
        name = str(one.get("name", ""))
        group = str(one.get("on") or "")
        if not group:
            out.append(
                from_rotation(
                    name,
                    "conditions",
                    one.get("origin") or (0, 0, 0),
                    one.get("rotate") or (0, 0, 0),
                )
            )
            continue
        face = (regions.get(group) or [None])[0]
        direction = (face or {}).get("normal") or (face or {}).get("axis")
        if not face or not direction:
            missing.append(name)
            continue
        out.append(from_face(name, "conditions", face["centroid"], direction))
    return out, missing
