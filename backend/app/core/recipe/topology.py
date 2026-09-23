"""영역과 바디를 **좌표 지문**으로 — 해석이 STEP 에서 같은 자리를 다시 집게.

해석(SimEngBay → Ansys Mechanical)은 우리가 보낸 STEP 을 임포트해 경계조건을 붙인다. 그런데
**STEP 은 이름표를 못 나른다.** 실측(2026-09-23): 이름표 붙은 조립을 `export_step` 으로 쓰면
조립 구조(`PRODUCT` · `NEXT_ASSEMBLY_USAGE_OCCURRENCE`)는 남고 ASCII 이름도 읽히지만,
**한글 이름은 깨진다** — 파일에 UTF-8 바이트가 아예 없고 되살릴 수 없었다.

그래서 이름에 기대지 않는다. 면은 **중심 · 법선 · 넓이**로, 바디는 **부피 · 무게중심 ·
경계상자**로 적어 보내고, 받는 쪽이 허용오차 안에서 짝짓는다. 규칙이 하나라 배울 것도 하나다.

**면 번호로 적지 않는 이유**는 더 크다. 실험계획(DOE)은 치수를 바꿔 형상을 여러 벌 만든다 —
「7번 면」 은 두께를 3 에서 10 으로 훑는 순간 다른 면을 가리킨다. 영역은 **셀렉터**(기하 조건,
`query.find_features` 의 말)로 적어 두고 **설계점마다 다시 푼다**. 그래서 이 모듈은 형상 하나를
받아 그때의 좌표를 낸다.

자세한 설계는 `docs/해석-조건-설계.md`, 받는 쪽 계약은 SimEngBay 의 `docs/해석-연동-계획.md`
「0단계 — CAD 계약」.
"""

from __future__ import annotations

import re
from typing import Any

from build123d import Shape

from app.core.recipe.query import find_features

#: 기본 영역 — **지그 생성기가 이미 아는 것**을 이름으로 낸다. 사람이 조건 편집기에서 더 고르기
#: 전에도 「바닥 고정 모달」 한 줄기는 이것만으로 돈다.
DEFAULT_REGIONS: list[dict[str, Any]] = [
    # 바닥 고정의 자리. 볼트 고정 지그는 이 면으로 시험대에 앉는다.
    {"name": "fixed_base", "select": {"what": "faces", "role": "bottom"}},
    # 볼트 · 핀이 지나는 구멍의 안쪽 면. 볼트 예압 · 원통 구속이 여기 붙는다.
    {"name": "bolt_holes", "select": {"what": "faces", "kind": "cylinder"}, "axis": "z"},
]

_ASCII_OK = re.compile(r"[^A-Za-z0-9_]+")


def slug(name: str, *, fallback: str) -> str:
    """STEP 에 내보낼 ASCII 이름. **뜻을 나르는 것은 JSON 이고, 이것은 손잡이일 뿐이다.**

    한글 이름은 STEP 에서 깨지므로(모듈 머리말) 아스키만 남긴다. 남는 게 없으면 `fallback`
    (`body_1` 같은 순번)을 쓴다 — 뜻은 `topology.json` 의 `name` 이 들고 있고, 여기서 필요한
    것은 **그 파일과 STEP 을 잇는 고유하고 안정된 글자**뿐이다.
    """
    cleaned = _ASCII_OK.sub("_", name).strip("_")
    return cleaned.lower() if cleaned else fallback


def _labeled_children(shape: Shape) -> list[Shape]:
    """이름표가 **모두** 붙은 자식들. 하나라도 비면 조립으로 보지 않는다."""
    children = list(getattr(shape, "children", ()) or ())
    if children and all(getattr(child, "label", "") for child in children):
        return children
    return []


def _xyz(v: Any) -> list[float]:
    return [round(float(v.X), 3), round(float(v.Y), 3), round(float(v.Z), 3)]


def _body_row(index: int, part: Shape, name: str) -> dict[str, Any]:
    box = part.bounding_box()
    return {
        "name": name,
        "step_product": slug(name, fallback=f"body_{index}"),
        "volume": round(float(part.volume), 3),
        "centroid": _xyz(part.center()),
        "bbox": [_xyz(box.min), _xyz(box.max)],
    }


def bodies(shape: Shape) -> list[dict[str, Any]]:
    """솔리드마다 한 줄 — 물성 · 메시 설정이 **어디에** 붙는지 가리킬 손잡이.

    조립이면 이름표 붙은 구성품마다, 아니면 통째로 하나다. 순서는 레시피가 만든 순서라 설계점이
    바뀌어도 같다 — 그래도 받는 쪽은 **부피 · 무게중심으로 짝짓는다**(순서에 기대지 않는다).
    """
    children = _labeled_children(shape)
    if children:
        return [
            _body_row(i, child, str(getattr(child, "label", "") or f"body_{i}"))
            for i, child in enumerate(children, start=1)
        ]
    return [_body_row(1, shape, "전체")]


def _face_fingerprint(row: dict[str, Any], face: Any) -> dict[str, Any]:
    """면 한 장의 지문 — SimEngBay 의 `regions` 계약이 기다리는 세 칸.

    **평면이 아닌 면은 `center()` 를 쓰지 않는다.** 실측(2026-09-23): 지름 8.5 구멍의
    원통면에서 `face.center()` 가 `[-34.25, -15, 5]` 를 준다 — 축이 아니라
    **표면 위의 점**(매개변수 한가운데)이다. 해석 쪽은 면의 넓이 무게중심을 내므로 같은
    구멍을 `[-30, -15, 5]` 로 부르고, 둘은 반지름만큼(4.25 mm) 어긋나 **짝이 안 맞는다.**
    경계상자 중심이 그 축 위의 점과 같다.
    """
    box = face.bounding_box()
    centroid = row["center"] if row.get("kind") == "plane" else _xyz((box.min + box.max) * 0.5)
    out: dict[str, Any] = {
        "centroid": centroid,
        "area": row["area"],
    }
    if row.get("normal") is not None:
        out["normal"] = row["normal"]
    # 원통면은 반지름 · 축이 짝짓기를 훨씬 쉽게 만든다 — 구멍은 중심만으로는 서로 닮았다.
    if row.get("radius") is not None:
        out["radius"] = row["radius"]
    if isinstance(row.get("axis"), dict):
        out["axis"] = row["axis"]["direction"]
    return out


def _edge_fingerprint(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"midpoint": row["midpoint"], "length": row["length"]}
    if row.get("radius") is not None:
        out["radius"] = row["radius"]
    return out


def _axis_matches(row: dict[str, Any], axis: str) -> bool:
    """원통면의 축이 이 방향인가. 수직 구멍만 고르는 데 쓴다."""
    direction = row.get("axis")
    if isinstance(direction, dict):
        direction = direction.get("direction")
    if not isinstance(direction, list) or len(direction) != 3:
        return False
    index = {"x": 0, "y": 1, "z": 2}[axis]
    return abs(direction[index]) > 0.95


def regions(
    shape: Shape, definitions: list[dict[str, Any]] | None = None
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """영역 이름 → 그때의 면(또는 엣지) 지문. 그리고 **못 푼 이름들**.

    못 푼 것을 조용히 빼지 않고 돌려주는 이유: 받는 쪽이 0개를 집으면 **하중 없는 해석**이
    끝까지 돌아 버린다. 어디서 끊겼는지는 이 목록이 유일한 증인이다.
    """
    found: dict[str, list[dict[str, Any]]] = {}
    unresolved: list[str] = []
    for definition in definitions if definitions is not None else DEFAULT_REGIONS:
        name = definition["name"]
        select = dict(definition.get("select") or {})
        answer = find_features(shape, select)
        rows = answer["items"]
        if definition.get("axis"):
            rows = [r for r in rows if _axis_matches(r, str(definition["axis"]))]
        if not rows:
            unresolved.append(name)
            continue
        if select.get("what") == "faces":
            faces = shape.faces()
            found[name] = [_face_fingerprint(r, faces[r["index"]]) for r in rows]
        else:
            found[name] = [_edge_fingerprint(r) for r in rows]
    return found, unresolved


def document(
    shape: Shape,
    definitions: list[dict[str, Any]] | None = None,
    *,
    units: str = "mm",
) -> dict[str, Any]:
    """`topology.json` 한 장. 설계점마다 하나씩 쓴다 — 같은 이름이라도 좌표가 다르다."""
    found, unresolved = regions(shape, definitions)
    return {
        "units": units,
        "bodies": bodies(shape),
        "regions": found,
        "unresolved": unresolved,
    }
