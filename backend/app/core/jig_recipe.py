"""생성기의 계획을 **레시피**로 — 지그가 STEP 한 덩어리가 아니라 변수 있는 도면으로 태어난다.

계획(FixturePlan)은 어디에 무엇을 놓나를 숫자로 안다. 그것을 box · cylinder · pin · bolt …
노드로 적으면 만든 지그를 **이어 그리고**, `판_두께` · `받침_높이` 같은 변수를 조립 → DOE 로
훑을 수 있다. 자리(받침 · 핀 · 클램프 위치)는 부품에서 나온 수라 그대로 적고, 사람이 바꿀 만한
치수만 변수로 뺀다.

노드 id 는 화면 · 미리보기의 이름표와 같은 말(바닥판 · 받침_1 · 위치_핀_1 · 클램프_1 … — id
에는 띄어쓰기를 못 써 밑줄)이라 간섭 보고와 도면 목록이 같은 이름을 쓴다.
"""

from __future__ import annotations

import math
from typing import Any

from app.core.model import FixturePlan
from app.core.options import JigOptions

Node = dict[str, Any]


def _r(value: float) -> float:
    return round(float(value), 3)


def _plate_nodes(plan: FixturePlan, params: dict[str, float], kind: str) -> list[Node]:
    plate = plan.base_plate
    params["판_길이"] = _r(plate.length)
    params["판_너비"] = _r(plate.width)
    params["판_두께"] = _r(plate.thickness)
    label = "바닥" if kind == "drop" else "바닥판"
    nodes: list[Node] = [
        {
            "id": label,
            "op": "box",
            "length": "=판_길이",
            "width": "=판_너비",
            "height": "=판_두께",
            "at": [0, 0, 0],
            "align": ["center", "center", "max"],
        }
    ]
    holes: list[tuple[float, list[list[float]]]] = []
    if plate.mount_hole_diameter > 0:
        margin = max(plate.mount_hole_diameter, 8.0)
        dx, dy = plate.length / 2 - margin, plate.width / 2 - margin
        if dx > margin and dy > margin:
            holes.append(
                (
                    plate.mount_hole_diameter,
                    [[_r(sx * dx), _r(sy * dy)] for sx in (-1, 1) for sy in (-1, 1)],
                )
            )
    by_diameter: dict[float, list[list[float]]] = {}
    for x, y, diameter in plate.holes:
        by_diameter.setdefault(_r(diameter), []).append([_r(x), _r(y)])
    holes += list(by_diameter.items())
    last = label
    for index, (diameter, points) in enumerate(holes, start=1):
        hole_id = f"{label}_구멍_{index}" if len(holes) > 1 else f"{label}_구멍"
        nodes.append(
            {
                "id": hole_id,
                "op": "hole",
                "target": last,
                "diameter": _r(diameter),
                "at": points,
            }
        )
        last = hole_id
    return nodes


def _clamped(plan: FixturePlan, opts: JigOptions, params: dict[str, float]) -> list[Node]:
    nodes: list[Node] = []
    params["받침_높이"] = _r(plan.product_lift)
    if plan.supports:
        params["받침_지름"] = _r(plan.supports[0].diameter)
    for i, support in enumerate(plan.supports, start=1):
        x, y, _ = support.position
        nodes.append(
            {
                "id": f"받침_{i}",
                "op": "cylinder",
                "radius": "=받침_지름/2",
                "height": "=받침_높이",
                "at": [_r(x), _r(y), 0],
                "align": ["center", "center", "min"],
            }
        )
    pins = rests = 0
    for locator in plan.locators:
        x, y, z = locator.position
        if locator.kind == "pin":
            pins += 1
            assert locator.diameter is not None and locator.engagement is not None
            nodes.append(
                {
                    "id": f"위치_핀_{pins}",
                    "op": "pin",
                    "at": [_r(x), _r(y), 0],
                    "diameter": _r(locator.diameter),
                    "length": f"=받침_높이 + {_r(locator.engagement)}",
                }
            )
        else:
            rests += 1
            assert locator.size is not None
            w, d, h = locator.size
            ix, iy, _ = locator.direction
            length, depth = (d, w) if abs(ix) > abs(iy) else (w, d)
            nodes.append(
                {
                    "id": f"받침대_{rests}",
                    "op": "box",
                    "length": _r(length),
                    "width": _r(depth),
                    "height": f"=받침_높이 + {_r(z + h / 2)}",
                    "at": [_r(x), _r(y), 0],
                    "align": ["center", "center", "min"],
                }
            )
    if plan.clamps:
        params["클램프_패드_지름"] = _r(plan.clamps[0].pad_diameter)
    for i, clamp in enumerate(plan.clamps, start=1):
        px, py, _ = clamp.post_position
        x, y, z = clamp.pad_position
        clearance = opts.clamp_clearance_above
        arm_bottom = f"받침_높이 + {_r(z + clearance)}"
        dx, dy = x - px, y - py
        reach = math.hypot(dx, dy) + opts.clamp_post_size / 2
        angle = math.degrees(math.atan2(dy, dx))
        post = f"클램프_{i}_기둥"
        arm_raw = f"클램프_{i}_팔_자리"
        arm = f"클램프_{i}_팔"
        pad = f"클램프_{i}_패드"
        nodes += [
            {
                "id": post,
                "op": "box",
                "length": _r(opts.clamp_post_size),
                "width": _r(opts.clamp_post_size),
                "height": f"={arm_bottom} + {_r(clamp.arm_thickness)}",
                "at": [_r(px), _r(py), 0],
                "align": ["center", "center", "min"],
            },
            {
                "id": arm_raw,
                "op": "box",
                "length": _r(reach),
                "width": _r(clamp.arm_width),
                "height": _r(clamp.arm_thickness),
                "at": [0, 0, 0],
                "align": ["min", "center", "min"],
            },
            {
                "id": arm,
                "op": "transform",
                "target": arm_raw,
                "rotate": [0, 0, _r(angle)],
                "translate": [_r(px), _r(py), f"={arm_bottom}"],
            },
            {
                "id": pad,
                "op": "cylinder",
                "radius": "=클램프_패드_지름/2",
                "height": _r(clearance),
                "at": [_r(x), _r(y), f"=받침_높이 + {_r(z)}"],
                "align": ["center", "center", "min"],
            },
            {"id": f"클램프_{i}", "op": "union", "targets": [post, arm, pad]},
        ]
    return nodes


def _bolted(plan: FixturePlan, params: dict[str, float]) -> list[Node]:
    nodes: list[Node] = []
    lift = plan.product_lift
    if lift > 0:
        params["스페이서_높이"] = _r(lift)
    for i, bolt in enumerate(plan.bolts, start=1):
        x, y, top = bolt.position
        seat = f"=스페이서_높이 + {_r(top)}" if lift > 0 else _r(top)
        length = (
            f"=스페이서_높이 + {_r(bolt.grip - lift + bolt.engagement)}"
            if lift > 0
            else _r(bolt.grip + bolt.engagement)
        )
        if lift > 0:
            outer = max(bolt.hole_diameter * 2.2, bolt.hole_diameter + 6)
            nodes.append(
                {
                    "id": f"스페이서_{i}",
                    "op": "standoff",
                    "at": [_r(x), _r(y), 0],
                    "outer": _r(outer),
                    "hole": _r(bolt.hole_diameter),
                    "height": "=스페이서_높이",
                }
            )
        nodes.append(
            {
                "id": f"볼트_{i}",
                "op": "bolt",
                "at": [_r(x), _r(y), seat],
                "nominal": _r(bolt.nominal),
                "length": length,
                "head": bolt.head,
                "washer": bolt.washer,
                "down": True,
            }
        )
    return nodes


def _bending(plan: FixturePlan, params: dict[str, float]) -> list[Node]:
    nodes: list[Node] = []
    lift = plan.product_lift
    params["받침_높이"] = _r(lift)
    rollers = plan.rollers
    if not rollers:
        return nodes
    params["롤러_지름"] = _r(rollers[0].diameter)
    params["스팬"] = _r(2 * max(abs(rollers[0].position[0]), abs(rollers[0].position[1])))
    along = rollers[0].along
    for i, one in enumerate(rollers, start=1):
        x, y, _ = one.position
        span_axis = "x" if along == "y" else "y"  # 롤러 축과 수직인 쪽이 스팬
        sign = 1 if (x if span_axis == "x" else y) >= 0 else -1
        at = (
            ["=스팬/2" if sign > 0 else "=-스팬/2", _r(y)]
            if span_axis == "x"
            else [_r(x), "=스팬/2" if sign > 0 else "=-스팬/2"]
        )
        nodes += [
            {
                "id": f"롤러_{i}_받침대",
                "op": "box",
                "length": _r(one.diameter if along == "y" else one.length),
                "width": _r(one.length if along == "y" else one.diameter),
                "height": "=받침_높이 - 롤러_지름/2",
                "at": [*at, 0],
                "align": ["center", "center", "min"],
            },
            {
                "id": f"롤러_{i}_원통",
                "op": "cylinder",
                "radius": "=롤러_지름/2",
                "height": _r(one.length),
                "axis": along.upper(),
                "at": [*at, "=받침_높이 - 롤러_지름/2"],
            },
            {
                "id": f"롤러_{i}",
                "op": "union",
                "targets": [f"롤러_{i}_받침대", f"롤러_{i}_원통"],
            },
        ]
    nose = plan.nose
    if nose is not None:
        params["노즈_지름"] = _r(nose.diameter)
        x, y, z = nose.position
        top_of_part = _r(z - nose.diameter / 2)
        nodes += [
            {
                "id": "로딩_노즈_원통",
                "op": "cylinder",
                "radius": "=노즈_지름/2",
                "height": _r(nose.length),
                "axis": nose.along.upper(),
                "at": [_r(x), _r(y), f"=받침_높이 + {top_of_part} + 노즈_지름/2"],
            },
            {
                "id": "로딩_노즈_줄기",
                "op": "box",
                "length": "=노즈_지름",
                "width": "=노즈_지름",
                "height": _r(nose.stem_height),
                "at": [_r(x), _r(y), f"=받침_높이 + {top_of_part} + 노즈_지름/2"],
                "align": ["center", "center", "min"],
            },
            {
                "id": "로딩_노즈",
                "op": "union",
                "targets": ["로딩_노즈_원통", "로딩_노즈_줄기"],
            },
        ]
    return nodes


def _drop(plan: FixturePlan, params: dict[str, float]) -> list[Node]:
    nodes: list[Node] = []
    params["틈"] = _r(plan.product_lift)
    impactor = plan.impactor
    if impactor is None:
        return nodes
    params["낙하물_지름"] = _r(impactor.diameter)
    x, y, z = impactor.position
    if impactor.kind == "ball":
        base = _r(
            z - impactor.diameter / 2
        )  # 계획의 z 는 부품 좌표계(틈 전) — 틈은 변수로 더한다
        nodes.append(
            {
                "id": "임팩터",
                "op": "sphere",
                "radius": "=낙하물_지름/2",
                "at": [_r(x), _r(y), f"=틈 + {base} + 낙하물_지름/2"],
            }
        )
    else:
        tip = _r(z)
        nodes += [
            {
                "id": "임팩터_끝",
                "op": "sphere",
                "radius": "=낙하물_지름/8",
                "at": [_r(x), _r(y), f"=틈 + {tip} + 낙하물_지름/8"],
            },
            {
                "id": "임팩터_몸",
                "op": "cone",
                "bottom_radius": "=낙하물_지름/2",
                "top_radius": "=낙하물_지름/8",
                "height": "=낙하물_지름*2",
                "at": [_r(x), _r(y), f"=틈 + {tip} + 낙하물_지름/8"],  # 원뿔의 at 은 밑면
            },
            {"id": "임팩터", "op": "union", "targets": ["임팩터_끝", "임팩터_몸"]},
        ]
    return nodes


def recipe_of(
    plan: FixturePlan, opts: JigOptions, *, product_label: str = "부품"
) -> dict[str, Any]:
    """계획 → 레시피. 부품은 들지 않는다(지그만) — 부품은 조립에서 `component` 로 온다."""
    params: dict[str, float] = {}
    nodes = _plate_nodes(plan, params, plan.kind)
    if plan.kind == "clamped":
        nodes += _clamped(plan, opts, params)
    elif plan.kind == "bolted":
        nodes += _bolted(plan, params)
    elif plan.kind == "bending":
        nodes += _bending(plan, params)
    elif plan.kind == "drop":
        nodes += _drop(plan, params)
    # 묶음 — 최종 피처 하나만 대상으로(중간 피처는 이미 그 안에).
    consumed: set[str] = set()
    for one in nodes:
        for key in ("target", "targets"):
            value = one.get(key)
            if isinstance(value, str):
                consumed.add(value)
            elif isinstance(value, list):
                consumed.update(value)
    leaves = [one["id"] for one in nodes if one["id"] not in consumed]
    nodes.append({"id": "지그", "op": "group", "targets": leaves})
    del product_label  # 메모는 버전 note 가 든다 — 레시피에는 없는 칸
    return {"version": 1, "params": params, "nodes": nodes, "result": "지그"}
