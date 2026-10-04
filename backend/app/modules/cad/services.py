"""레시피 평가 — 상태 없는 층.

레시피는 두 길로 만들어진다:
- **미리보기**(`build`) — 편집기가 칸을 고칠 때마다. 요청 안에서 동기로. 작으면 수십 ms.
- **버전 평가**(`Job(kind="cad")`) — 저장한 버전의 STEP · glTF 를 작업물로 남긴다. 워커가 돈다.

두 길이 같은 `core.recipe.evaluate` 를 지난다. 버전 · 작업(work) 은 `modules/works` 가 든다.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core import export, shape_index
from app.core.recipe import Evaluation, RecipeError, evaluate, parse
from app.core.recipe.digest import digest
from app.core.recipe.schema import RecipeValidationError
from app.core.recipe.unfold import Unfolded, UnfoldError
from app.core.recipe.unfold import unfold as unfold_shape
from app.modules.jobs import registry
from app.modules.jobs.models import Artifact
from app.shared import filestore
from app.shared.errors import AppError, code

logger = logging.getLogger(__name__)

JOB_KIND = "cad"


# --- 레시피 -------------------------------------------------------------------


def resolve_import(key: str) -> Path:
    """`import_step` 노드의 `file` — 작업물 id 다. 워커 · 미리보기 · 지그 작업이 같은 규칙을
    쓴다."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        artifact = db.get(Artifact, uuid.UUID(key))
        if artifact is None:
            raise ValueError(f"작업물({key})을 찾을 수 없습니다.")
        return filestore.resolve(artifact.path)
    finally:
        db.close()


def resolve_component(key: str) -> dict[str, Any]:
    """`component` 의 `source` → 그 도면의 **레시피**.

    열쇠는 `part:<id>` · `jig:<id>` · `work:<id>`, `@<번호>` 로 버전을 집는다(없으면 현재).
    조립은 **살아 있는 레시피**를 가져온다 — STEP 을 박아 넣는 것과 달라서, 가져온 쪽의 변수를
    덮어써 조립의 변수로 움직일 수 있다."""
    from app.database import SessionLocal
    from app.modules.jigs.models import Jig, JigVersion
    from app.modules.parts.models import Part, PartVersion
    from app.modules.works.models import Work, WorkVersion

    kind, _, rest = key.partition(":")
    name, _, raw_number = rest.partition("@")
    number = int(raw_number) if raw_number else None
    db = SessionLocal()
    try:
        identifier = uuid.UUID(name)
        version: Any = None
        if kind == "part":
            part = db.get(Part, identifier)
            if part is None:
                raise ValueError(f"부품({name})을 찾을 수 없습니다.")
            version = db.scalar(
                select(PartVersion).where(
                    PartVersion.part_id == part.id,
                    PartVersion.number == (number or part.current_version),
                )
            )
        elif kind == "jig":
            jig = db.get(Jig, identifier)
            if jig is None:
                raise ValueError(f"지그({name})를 찾을 수 없습니다.")
            version = db.scalar(
                select(JigVersion).where(
                    JigVersion.jig_id == jig.id,
                    JigVersion.number == (number or jig.current_version),
                )
            )
            if version is not None and not getattr(version, "recipe", None):
                # 지그 카탈로그의 버전은 레시피 대신 생성 작업을 들고 있을 수 있다.
                raise ValueError(
                    "이 지그 버전에는 레시피가 없습니다. 레시피로 모델링한 지그만 "
                    "가져올 수 있습니다."
                )
        elif kind == "work":
            work = db.get(Work, identifier)
            if work is None:
                raise ValueError(f"작업({name})을 찾을 수 없습니다.")
            version = db.scalar(
                select(WorkVersion).where(
                    WorkVersion.work_id == work.id,
                    WorkVersion.number == (number or work.current_version),
                )
            )
        else:
            raise ValueError(
                f"알 수 없는 참조 키({key})입니다. part:, jig:, work: 중 하나를 사용하십시오."
            )
        if version is None:
            raise ValueError(f"버전({key})을 찾을 수 없습니다.")
        return dict(version.recipe)
    finally:
        db.close()


def check(raw: dict[str, Any]) -> list[str]:
    """만들지 않고 모양만 본다. 비어 있으면 통과."""
    try:
        parse(raw)
    except RecipeValidationError as failure:
        return failure.problems
    return []


def patch(raw: dict[str, Any], ops: list[dict[str, Any]]) -> dict[str, Any]:
    """연산 몇 개로 고친 레시피 — 고친 뒤 검사까지. 문제가 있으면 고친 레시피와 함께 말한다."""
    from app.core.recipe.patch import PatchError, apply

    try:
        made = apply(raw, ops)
    except PatchError as failure:
        raise AppError(code("CAD", 10), str(failure)) from failure
    return {"recipe": made, "problems": check(made)}


def place(
    raw: dict[str, Any], *, mover: str, onto: str, face: str, offset: float, align: str
) -> dict[str, Any]:
    """구성품 `mover` 를 `onto` 의 면에 얹는다 — translate 를 계산해 넣은 레시피와 그 값.

    둘 다 이 레시피의 피처여야 하고, mover 는 translate 를 갖는 것(component · transform)이어야
    한다. 상자는 평가 결과(node 별 bbox)에서 온다."""
    from app.core.recipe.patch import PatchError, apply, place_on

    evaluation = build(raw)
    boxes = {one.id: one.bbox for one in evaluation.nodes}
    if mover not in boxes or onto not in boxes:
        raise AppError(code("CAD", 11), f"피처({mover}, {onto})를 찾을 수 없습니다.")
    node = next((n for n in raw.get("nodes", []) if n.get("id") == mover), None)
    if node is None or node.get("op") not in ("component", "transform"):
        raise AppError(
            code("CAD", 11), f"‘{mover}’: component 또는 transform 피처만 이동할 수 있습니다."
        )
    current = [
        float(v) if not isinstance(v, str) else 0.0 for v in node.get("translate") or [0, 0, 0]
    ]
    if any(isinstance(v, str) for v in node.get("translate") or []):
        raise AppError(
            code("CAD", 11),
            f"‘{mover}’: translate 값에 식이 포함되어 있어 위치를 계산할 수 없습니다.",
        )
    mbox, tbox = boxes[mover], boxes[onto]
    if mbox is None or tbox is None:
        raise AppError(code("CAD", 11), "경계 상자를 계산할 수 없는 피처입니다(스케치 등).")
    try:
        translate = place_on(mbox, current, tbox, face=face, offset=offset, align=align)
    except PatchError as failure:
        raise AppError(code("CAD", 11), str(failure)) from failure
    made = apply(
        raw, [{"op": "set_field", "id": mover, "field": "translate", "value": translate}]
    )
    return {"recipe": made, "translate": translate, "problems": check(made)}


def mate_pick(
    raw: dict[str, Any],
    *,
    node: str,
    side: str,
    what: str,
    point: list[float],
    target: str | None = None,
) -> dict[str, Any]:
    """3D 에서 누른 면 · 엣지를 **구속의 질의로** — `this` 는 구성품 자신의 좌표로 되돌려서.

    누른 자리는 조립의 좌표다. 구속의 `this` 는 가져온 도면의 좌표로 적어야 구성품이 어디로
    옮겨 가도 같은 면을 가리킨다 — 그래서 그 구성품의 지금 자리(회전 · 이동)를 거꾸로 걸어
    되돌린 점으로 고른다. 후보 중 **하나에만 맞는 것**을 고르고, 후보 전부도 함께 준다."""
    import numpy as np

    from app.core.recipe.query import selector_candidates

    nodes = list(raw.get("nodes") or [])
    ids = [str(one.get("id")) for one in nodes]
    if node not in ids:
        raise AppError(code("CAD", 19), f"‘{node}’ 피처가 존재하지 않습니다.")
    mover = nodes[ids.index(node)]
    if mover.get("op") != "component":
        raise AppError(code("CAD", 19), f"‘{node}’: 가져온 구성품(component)이 아닙니다.")
    if side == "to":
        if target is None or target not in ids[: ids.index(node)]:
            raise AppError(
                code("CAD", 19),
                "target: 구속은 이 구성품보다 앞에 있는 피처에만 지정할 수 있습니다.",
            )
        shape = build({**raw, "nodes": nodes[: ids.index(target) + 1], "result": None}).shape
        at = list(point)
    else:
        # 지금 자리 — 구속이 아직 안 맞으면(고치는 중) 손으로 놓은 자리로.
        upto = nodes[: ids.index(node) + 1]
        try:
            info = build({**raw, "nodes": upto, "result": node}).nodes[-1]
        except AppError:
            info = build({**raw, "nodes": [*upto[:-1], {**mover, "mates": []}]}).nodes[-1]
        placed = info.placement or {}
        rotation = np.array(placed.get("rotation") or np.eye(3))
        moved = np.array(placed.get("translation") or [0.0, 0.0, 0.0])
        at = [float(v) for v in rotation.T @ (np.array(point, dtype=float) - moved)]
        alone = {**mover, "translate": [0, 0, 0], "rotate": [0, 0, 0], "mates": []}
        shape = build({**raw, "nodes": [alone], "result": None}).shape
    try:
        found = selector_candidates(shape, {"what": what, "point": at})
    except ValueError as failure:
        raise AppError(code("CAD", 19), str(failure)) from failure
    candidates = found["candidates"]
    best = next(
        (one for one in candidates if one["matches"] == 1 and one["stable"]),
        next((one for one in candidates if one["matches"] == 1), None),
    )
    if best is None:
        raise AppError(
            code("CAD", 19), "선택한 위치에서 면 또는 엣지를 하나로 특정하지 못했습니다."
        )
    return {"select": best["select"], "label": best["label"], "candidates": candidates}


#: 조립 간섭의 기본 허용치(mm³) — 닿는 면의 수치 오차가 이 아래로 나온다(지그 생성기와 같다).
DEFAULT_INTERFERENCE_TOLERANCE = 0.5


def interference(raw: dict[str, Any], *, tolerance: float | None = None) -> dict[str, Any]:
    """레시피의 **구성품끼리** 겹침 — 결과가 이름표 붙은 묶음(group)일 때 그 자식들의 모든 쌍.

    구성품이 하나뿐이거나 묶음이 아니면 검사할 쌍이 없다 — `parts` 가 그것을 말한다."""
    from app.core.interference import check_pairs
    from app.core.recipe.evaluate import _labeled_children

    evaluation = build(raw)
    children = _labeled_children(evaluation.shape)
    limit = DEFAULT_INTERFERENCE_TOLERANCE if tolerance is None else tolerance
    report = check_pairs([(str(child.label), child) for child in children], limit)
    return {
        **report.summary(),
        "parts": [str(child.label) for child in children],
        "checked_pairs": len(children) * (len(children) - 1) // 2,
    }


def cut_list(raw: dict[str, Any], node_id: str) -> dict[str, Any]:
    """구조 프레임의 **절단 목록** — 부재마다 자를 길이 · 끝의 각 · 부피. 프레임은 앞 노드를
    가리키지 않으므로 레시피를 풀기만(변수 식) 하고 그 노드만 만든다."""
    from app.core.recipe import schema as recipe_schema
    from app.core.recipe.frame import FrameError
    from app.core.recipe.frame import cut_list as frame_cut_list

    try:
        recipe = parse(raw)
    except RecipeValidationError as failure:
        raise AppError(
            code("CAD", 2),
            "레시피가 올바르지 않습니다.",
            details={"problems": failure.problems},
        ) from failure
    node = next((one for one in recipe.nodes if one.id == node_id), None)
    if not isinstance(node, recipe_schema.FrameNode):
        raise AppError(code("CAD", 15), f"‘{node_id}’: 구조 프레임(frame)이 아닙니다.")
    try:
        return {"node": node_id, **frame_cut_list(node)}
    except FrameError as failure:
        raise AppError(code("CAD", 15), str(failure)) from failure


def unfold(
    raw: dict[str, Any], *, k_factor: float, flip: bool = False, node: str | None = None
) -> Unfolded:
    """레시피의 결과(또는 `node`)를 만들어 **전개도**로 편다. 펼 수 없으면 까닭과 함께 400."""

    evaluation = build({**raw, "result": node} if node else raw)
    try:
        return unfold_shape(evaluation.shape, k_factor=k_factor, flip=flip)
    except UnfoldError as failure:
        raise AppError(code("CAD", 17), f"전개할 수 없습니다: {failure}") from failure


def solve_sketch(shape: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """구속 윤곽 하나를 풀어 점의 자리와 남은 움직임 — 캔버스가 푼 모양을 그린다."""
    from app.core.recipe import schema as recipe_schema
    from app.core.recipe.sketch_solver import SketchSolveError, solve

    try:
        recipe = parse(
            {"params": params, "nodes": [{"id": "s", "op": "sketch", "shapes": [shape]}]}
        )
    except RecipeValidationError as failure:
        raise AppError(
            code("CAD", 21),
            "구속 윤곽이 올바르지 않습니다.",
            details={"problems": failure.problems},
        ) from failure
    node = recipe.nodes[0]
    assert isinstance(node, recipe_schema.SketchNode)
    one = node.shapes[0]
    if not isinstance(one, recipe_schema.ConstrainedShape):
        raise AppError(code("CAD", 21), "구속 윤곽(type: constrained)이 아닙니다.")
    try:
        solved = solve(one)
    except SketchSolveError as failure:
        raise AppError(code("CAD", 21), str(failure)) from failure
    return {
        "points": {name: [round(x, 6), round(y, 6)] for name, (x, y) in solved.points.items()},
        "free": solved.free,
    }


def mid_surface(raw: dict[str, Any], *, node: str | None = None) -> Any:
    """레시피의 결과(또는 `node`)를 만들어 **중간면**으로. 판이 아니면 까닭과 함께 400."""
    from app.core.recipe.midsurface import MidSurfaceError, midsurface

    evaluation = build({**raw, "result": node} if node else raw)
    try:
        return midsurface(evaluation.shape)
    except MidSurfaceError as failure:
        raise AppError(
            code("CAD", 20), f"중간면을 추출하지 못했습니다: {failure}"
        ) from failure


def drawing_sheet(
    raw: dict[str, Any],
    *,
    title: str = "",
    sheet: str = "A3",
    material: str = "",
    note: str = "",
    node: str | None = None,
) -> Any:
    """레시피의 결과(또는 `node`)를 만들어 **도면 한 장**으로."""
    from app.core import drawing

    evaluation = build({**raw, "result": node} if node else raw)
    try:
        return drawing.make_sheet(
            evaluation.shape, title=title, sheet=sheet, material=material, note=note
        )
    except ValueError as failure:
        raise AppError(code("CAD", 18), f"도면을 생성하지 못했습니다: {failure}") from failure


def build(raw: dict[str, Any], *, allow_sketch: bool = False) -> Evaluation:
    """만들어 본다. 실패는 AppError — 메시지가 그대로 화면 · AI 에 간다. `allow_sketch` 는
    미리보기(info · preview · mesh)만 — 그리는 도중의 2D 도 보여 줘야 한다."""
    try:
        recipe = parse(raw)
    except RecipeValidationError as failure:
        raise AppError(
            code("CAD", 2),
            "레시피가 올바르지 않습니다.",
            details={"problems": failure.problems},
        ) from failure
    try:
        return evaluate(
            recipe,
            resolve_file=resolve_import,
            resolve_component=resolve_component,
            allow_sketch=allow_sketch,
        )
    except RecipeError as failure:
        raise AppError(
            code("CAD", 3),
            f"형상을 생성하지 못했습니다: {failure.message}",
            details={"node_id": failure.node_id},
        ) from failure


# --- Job kind="cad" -------------------------------------------------------------


def sweep(
    raw: dict[str, Any], *, param: str, values: list[float], material: str | None = None
) -> list[dict[str, Any]]:
    """치수 하나를 값마다 바꿔 가며 만들어 보고 **치수표를 나란히** 돌려준다.

    「연결부는 그대로 두고 두께만 바꿔 가며 알맞은 것을 찾는다」 가 이 한 번의 부름으로 된다.
    실패한 값은 그 이유와 함께 남는다 — 끊기지 않게(가느다란 값에서 형상이 깨지는 일은 흔하다).
    """
    params = raw.get("params") or {}
    if param not in params:
        known = ", ".join(sorted(params)) or "(없음)"
        raise AppError(
            code("CAD", 10),
            f"레시피에 ‘{param}’ 치수가 없습니다.",
            details={"known": known},
        )
    if len(values) > 40:
        raise AppError(code("CAD", 11), "한 번에 최대 40개 값까지 계산할 수 있습니다.")
    out: list[dict[str, Any]] = []
    for value in values:
        variant = {**raw, "params": {**params, param: value}}
        try:
            evaluation = build(variant)
        except AppError as failure:
            out.append({param: value, "ok": False, "error": failure.message})
            continue
        out.append(
            {param: value, "ok": True, "geometry": digest(evaluation.shape, material=material)}
        )
    return out


def run_job(
    input: dict[str, Any],
    options: dict[str, Any],
    out_dir: Path,
    progress: registry.Progress,
) -> registry.Outcome:
    """버전의 레시피를 만들어 STEP · glTF 를 남긴다."""
    del options
    import time

    started = time.perf_counter()
    try:
        recipe = parse(dict(input["recipe"]))
    except RecipeValidationError as failure:
        raise registry.UserFacingError(" / ".join(failure.problems)) from failure
    try:
        evaluation = evaluate(
            recipe, resolve_file=resolve_import, resolve_component=resolve_component
        )
    except RecipeError as failure:
        raise registry.UserFacingError(f"{failure.node_id}: {failure.message}") from failure
    progress(
        "evaluate",
        int((time.perf_counter() - started) * 1000),
        f"노드 {len(evaluation.nodes)}개",
    )

    started = time.perf_counter()
    step = export.write_step(evaluation.shape, out_dir / "model.step")
    glb = export.write_gltf(evaluation.shape, out_dir / "model.glb")
    progress("export", int((time.perf_counter() - started) * 1000), "STEP · glTF")

    # 형상으로 찾을 수 있게 — 만든 김에 색인을 요약에 적는다(`core/shape_index.py`).
    started = time.perf_counter()
    summary = evaluation.summary()
    summary["shape"] = shape_index.safe_index(evaluation.shape, dict(input["recipe"]))
    progress("index", int((time.perf_counter() - started) * 1000), "형상 색인")

    return registry.Outcome(
        summary=summary,
        artifacts=[
            registry.ArtifactSpec(
                kind="model_step", path=step, content_type="application/step"
            ),
            registry.ArtifactSpec(
                kind="model_glb", path=glb, content_type="model/gltf-binary"
            ),
        ],
    )
