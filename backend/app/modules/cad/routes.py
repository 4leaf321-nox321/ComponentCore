"""CAD 라우터 — 레시피의 스키마 · 검증 · 미리보기 · 내려받기. **상태가 없다.**

미리보기는 요청 안에서 동기로 만든다 — 편집기가 칸을 고칠 때마다 부르는 길이라 큐를 거치면
느리다. 저장은 남의 일이다: 버전은 `modules/works`, 시작점은 `modules/templates`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core import export, vibration
from app.core.recipe import describe
from app.core.recipe import templates as recipe_templates
from app.core.recipe.digest import digest
from app.core.recipe.mesh import mesh
from app.modules.accounts.models import User
from app.modules.cad import services
from app.modules.cad.schemas import (
    BeamRequest,
    ConditionNotesRequest,
    CutListRequest,
    DrawingRequest,
    FindRequest,
    FramesRequest,
    GeometryRequest,
    InterferenceRequest,
    MatePickRequest,
    MeasureRequest,
    MidSurfaceRequest,
    PatchRequest,
    PlaceRequest,
    RecipeInfoOut,
    RecipeProblemsOut,
    RecipeRequest,
    RecipeSchemaOut,
    SelectorsRequest,
    SketchSolveRequest,
    SweepRequest,
    UnfoldRequest,
    ViewsRequest,
)
from app.shared.auth import current_user
from app.shared.errors import AppError, code

router = APIRouter(prefix="/cad", tags=["cad"])


# --- 레시피 -------------------------------------------------------------------


@router.get("/recipe/schema", response_model=RecipeSchemaOut, response_model_by_alias=True)
def recipe_schema(_: User = Depends(current_user)) -> RecipeSchemaOut:
    """노드 종류 · 칸 · 템플릿. **화면이 목록을 손으로 들지 않는다** — 연산을 더하면 편집기가
    따라온다."""
    return RecipeSchemaOut(
        schema=describe(),
        templates=recipe_templates.all_templates(),
        template_labels=recipe_templates.TEMPLATE_LABELS,
    )


@router.post("/recipe/check", response_model=RecipeProblemsOut)
def recipe_check(payload: RecipeRequest, _: User = Depends(current_user)) -> RecipeProblemsOut:
    """모양만 본다(만들지 않는다). 편집기가 칸을 고칠 때마다 부른다."""
    problems = services.check(payload.recipe)
    return RecipeProblemsOut(ok=not problems, problems=problems)


@router.post("/recipe/info", response_model=RecipeInfoOut)
def recipe_info(payload: RecipeRequest, _: User = Depends(current_user)) -> RecipeInfoOut:
    """만들어 본 요약(크기 · 부피 · 노드별 정보). 실패하면 어느 노드가 왜인지."""
    return RecipeInfoOut(summary=services.build(payload.recipe, allow_sketch=True).summary())


@router.post("/recipe/preview")
def recipe_preview(payload: RecipeRequest, _: User = Depends(current_user)) -> Response:
    """미리보기 glTF. 스케치까지만 그렸으면 면으로 보인다."""
    evaluation = services.build(payload.recipe, allow_sketch=True)
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "preview.glb"
        export.write_gltf(evaluation.shape, target)
        return Response(target.read_bytes(), media_type="model/gltf-binary")


@router.post("/recipe/geometry")
def recipe_geometry(
    payload: GeometryRequest, _: User = Depends(current_user)
) -> dict[str, Any]:
    """**AI 가 읽는 치수표** — 크기 · 평면(법선 · 넓이) · 원통 · 구멍(지름 · 중심 · 깊이).

    사람은 3D 에서 면을 눌러 재지만 AI 는 못 본다. 메시 전체는 너무 크므로 설계에 쓰는 값만
    추려 준다 — 제품을 기준으로 지그를 그릴 때 이것을 먼저 본다."""
    evaluation = services.build(payload.recipe)
    return digest(evaluation.shape, material=payload.material)


@router.post("/recipe/sweep")
def recipe_sweep(payload: SweepRequest, _: User = Depends(current_user)) -> dict[str, Any]:
    """치수 하나를 값마다 바꿔 만들어 보고 치수표를 나란히 — **맞는 값을 찾아가는** 길.

    지그를 세트의 공진에 맞출 때처럼 「연결부는 그대로 두고 나머지를 바꿔 가며」 고르는 일에
    쓴다. 무엇이 어떻게 달라졌는지는 질량 · 관성 · 크기로 본다."""
    return {
        "param": payload.param,
        "results": services.sweep(
            payload.recipe,
            param=payload.param,
            values=payload.values,
            material=payload.material,
        ),
    }


@router.post("/recipe/views")
def recipe_views(payload: ViewsRequest, _: User = Depends(current_user)) -> dict[str, Any]:
    """은선 투영 그림 — iso · front · top · right 의 SVG 와 PNG(base64). AI 가 자기가 그린 것을
    눈으로 확인하는 길."""
    from app.core.views import views

    evaluation = services.build(payload.recipe)
    try:
        return {"views": views(evaluation.shape, tuple(payload.views), width=payload.width)}
    except ValueError as failure:
        raise AppError(code("CAD", 8), str(failure)) from failure


@router.post("/recipe/cutlist")
def recipe_cutlist(payload: CutListRequest, _: User = Depends(current_user)) -> dict[str, Any]:
    """구조 프레임의 **절단 목록** — 부재마다 자를 길이(가장 긴 데) · 끝의 자르는 각(0 = 직각)
    · 부피. 지그를 만들 때 그대로 재단 · 주문한다."""
    return services.cut_list(payload.recipe, payload.node)


@router.post("/recipe/find")
def recipe_find(payload: FindRequest, _: User = Depends(current_user)) -> dict[str, Any]:
    """말로 고른 엣지 · 면의 좌표 — 「윗면의 바깥 엣지」 「지름 8 구멍의 위 원」. 답의
    midpoint · center 를 fillet · chamfer 의 near, 스케치의 plane 에 그대로 쓴다.

    **선택 그룹의 셀렉터도 그대로 푼다** — 여럿을 묶은 합(`{"any": [...]}`)과 면 나누기의
    태그(`tag`)까지. 화면이 트리에서 고른 그룹을 3D 에 비출 때 쓴다."""
    from app.core.recipe.follow import resolved
    from app.core.recipe.params import ExpressionError, resolve_params
    from app.core.recipe.query import select_features

    evaluation = services.build(payload.recipe)
    # 그룹의 규칙에 도면 변수 식(`"radius": "=지름/2"`)이 있으면 지금 값으로 풀어 묻는다.
    try:
        (query,) = resolved([payload.query], resolve_params(payload.recipe))
    except ExpressionError as failure:
        raise AppError(
            code("CAD", 16), f"규칙의 식을 계산하지 못했습니다: {failure}"
        ) from failure
    return select_features(evaluation.shape, query, evaluation.tags)


@router.get("/conditions/schema")
def conditions_schema(_: User = Depends(current_user)) -> dict[str, Any]:
    """해석 조건의 **칸 사양표** — 화면이 폼을 그리고 AI 가 읽는 한 벌.

    종류를 더할 때 화면을 고치지 않게, 정본을 서버가 들고 준다(`core/conditions.py`)."""
    from app.core.conditions import spec

    return spec()


@router.post("/conditions/notes")
def conditions_notes(
    payload: ConditionNotesRequest, _: User = Depends(current_user)
) -> dict[str, Any]:
    """조건의 식 중 **풀리지 않는 것** — 고치는 중에 알린다(저장 · 내보내기에서 막히기 전에).
    고치는 중인 한 벌이라 검증하지 않는다 — 알림만 준다."""
    from app.core import conditions as condition_model

    items = condition_model.expression_notes(
        payload.conditions, payload.recipe.get("params") or {}
    )
    return {"items": items}


@router.post("/conditions/frames")
def conditions_frames(
    payload: FramesRequest, _: User = Depends(current_user)
) -> dict[str, Any]:
    """도면과 해석 조건의 **좌표계를 지금 치수로** 푼다 — 원점 · X · Y · Z. 조건 화면이 3D 에
    축을 그린다. 면에 붙인 좌표계는 그 선택 그룹을 지금 형상에서 풀어 얻는다.

    계산은 서버 한 곳이다(`core/frames`) — 화면이 따로 셈하면 3D 에 보인 방향과 내보낸
    방향이 어긋나는 날이 온다. 못 푼 이름은 `missing` 으로 돌려준다."""
    from app.core import conditions as condition_model
    from app.core import frames
    from app.core.recipe import topology

    evaluation = services.build(payload.recipe)
    raw = payload.conditions or {}
    try:
        resolved = condition_model.resolve(raw, payload.recipe.get("params") or {})
    except condition_model.ConditionError as failure:
        raise AppError(code("CAD", 14), str(failure)) from failure
    wanted = {
        str(one.get("on")) for one in resolved.get("coordinate_systems") or [] if one.get("on")
    }
    groups = [
        {"name": one["name"], "select": one.get("select") or {}}
        for one in resolved.get("named_selections") or []
        if one.get("name") in wanted
    ]
    regions, _unresolved = (
        topology.regions(evaluation.shape, groups, evaluation.tags) if groups else ({}, [])
    )
    side, missing = frames.condition_frames(resolved.get("coordinate_systems") or [], regions)
    return {"items": [*evaluation.frames, *side], "missing": missing}


@router.post("/recipe/selectors")
def recipe_selectors(
    payload: SelectorsRequest, _: User = Depends(current_user)
) -> dict[str, Any]:
    """3D 에서 **고른 것을 말로 되돌려 준다** — 「아래쪽 면」 · 「반지름 4.25 원통면(4개)」.

    좌표로 저장하면 실험계획이 치수를 바꾸는 순간 그 자리에 아무것도 없다. 후보를 여럿 주고
    **지금 몇 개에 맞는지**(`matches`)를 함께 보여 사람이 고르게 한다.

    `picks`(목록)를 주면 여럿을 한 번에 — `{"items": [...]}` 를 같은 순서로 돌려준다(사각형
    선택). 도면은 한 번만 만든다."""
    from app.core.recipe.query import selector_candidates

    evaluation = services.build(payload.recipe)
    try:
        if payload.picks is not None:
            shape = evaluation.shape
            return {"items": [selector_candidates(shape, one) for one in payload.picks]}
        return selector_candidates(evaluation.shape, payload.pick)
    except ValueError as failure:
        raise AppError(code("CAD", 13), str(failure)) from failure


@router.post("/recipe/bodies")
def recipe_bodies(payload: RecipeRequest, _: User = Depends(current_user)) -> dict[str, Any]:
    """이 도면의 **바디 목록** — 물성이 「어디에」 붙는지 고를 손잡이.

    조립이면 이름표 붙은 구성품마다 하나, 단품이면 「전체」 하나다. 이름은 **내보낼 때와
    같은 것**이다(`topology.bodies`) — 화면이 메시의 면에서 지어내면 두 곳이 어긋나는 날
    사람이 고른 이름이 폴더에 없는 이름이 된다.

    부피와 무게중심도 함께 준다 — 이름만으로는 어느 것이 어느 것인지 모를 때가 있다."""
    from app.core.recipe import topology

    evaluation = services.build(payload.recipe)
    return {"items": topology.bodies(evaluation.shape)}


@router.post("/recipe/measure")
def recipe_measure(payload: MeasureRequest, _: User = Depends(current_user)) -> dict[str, Any]:
    """둘 사이를 잰다 — 점 · 구멍 중심 · 면 · 엣지. 거리(축별 차) · 평면끼리 각도 · 간격."""
    from app.core.recipe.query import measure

    evaluation = services.build(payload.recipe)
    try:
        return measure(evaluation.shape, payload.a, payload.b)
    except ValueError as failure:
        raise AppError(code("CAD", 9), str(failure)) from failure


@router.post("/recipe/patch")
def recipe_patch(payload: PatchRequest, _: User = Depends(current_user)) -> dict[str, Any]:
    """연산 몇 개로 고친 레시피 + 검사 결과. 저장은 안 한다 — works 의 patch 가 저장한다."""
    return services.patch(payload.recipe, payload.ops)


@router.post("/recipe/place")
def recipe_place(payload: PlaceRequest, _: User = Depends(current_user)) -> dict[str, Any]:
    """구성품을 다른 것의 면에 얹는다 — 「지그 윗면에 부품 바닥을」. translate 를 계산해 넣은
    레시피를 돌려준다."""
    return services.place(
        payload.recipe,
        mover=payload.mover,
        onto=payload.onto,
        face=payload.face,
        offset=payload.offset,
        align=payload.align,
    )


@router.post("/recipe/mate-pick")
def recipe_mate_pick(
    payload: MatePickRequest, _: User = Depends(current_user)
) -> dict[str, Any]:
    """조립 구속을 **눌러서** — 3D 에서 누른 면 · 엣지를 구속의 `this` · `select` 질의로.
    `this` 는 구성품 자신(가져온 도면)의 좌표로 되돌려 고른다."""
    return services.mate_pick(
        payload.recipe,
        node=payload.node,
        side=payload.side,
        what=payload.what,
        point=payload.point,
        target=payload.target,
    )


@router.post("/recipe/interference")
def recipe_interference(
    payload: InterferenceRequest, _: User = Depends(current_user)
) -> dict[str, Any]:
    """조립의 구성품끼리 겹치는가 — 모든 쌍의 겹침 부피. 허용치(mm³) 이하는 닿은 것으로
    본다."""
    return services.interference(payload.recipe, tolerance=payload.tolerance)


@router.post("/recipe/mesh")
def recipe_mesh(payload: RecipeRequest, _: User = Depends(current_user)) -> dict[str, Any]:
    """면 · 엣지 단위 메시 + 요약 — 편집기의 미리보기이자 「3D 에서 고르기」 의 근거.
    스케치까지만 그렸으면 면으로 보인다."""
    evaluation = services.build(payload.recipe, allow_sketch=True)
    # 레시피의 좌표계도 함께 — 편집기가 3D 에 축을 그린다(계산은 서버 한 곳, `core/frames`).
    return {
        "summary": evaluation.summary(),
        "mesh": mesh(evaluation.shape),
        "frames": evaluation.frames,
        # 기준축 · 기준면 — 형상이 아니라 3D 에 따로 그린다.
        "datums": evaluation.datums,
    }


@router.post("/recipe/step")
def recipe_step(payload: RecipeRequest, _: User = Depends(current_user)) -> Response:
    """저장하지 않고 STEP 만 받는다 — 한 번 쓰고 말 도형."""
    evaluation = services.build(payload.recipe)
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "model.step"
        export.write_step(evaluation.shape, target)
        return Response(
            target.read_bytes(),
            media_type="application/step",
            headers={"Content-Disposition": 'attachment; filename="model.step"'},
        )


@router.post("/recipe/stl")
def recipe_stl(payload: RecipeRequest, _: User = Depends(current_user)) -> Response:
    """STL — 3D 프린터로 지그를 뽑을 때."""
    evaluation = services.build(payload.recipe)
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "model.stl"
        export.write_stl(evaluation.shape, target)
        return Response(
            target.read_bytes(),
            media_type="model/stl",
            headers={"Content-Disposition": 'attachment; filename="model.stl"'},
        )


@router.post("/recipe/dxf")
def recipe_dxf(payload: RecipeRequest, _: User = Depends(current_user)) -> Response:
    """DXF — 2D 도면. 스케치 · 단면이면 그대로, 입체면 **높이 절반의 단면**을 낸다."""
    evaluation = services.build(payload.recipe, allow_sketch=True)
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "model.dxf"
        export.write_dxf(evaluation.shape, target)
        return Response(
            target.read_bytes(),
            media_type="application/dxf",
            headers={"Content-Disposition": 'attachment; filename="model.dxf"'},
        )


@router.post("/recipe/unfold", response_model=None)
def recipe_unfold(
    payload: UnfoldRequest,
    format: str = Query(default="json", pattern="^(json|dxf|svg)$"),
    _: User = Depends(current_user),
) -> Response | dict[str, Any]:
    """**전개도** — 굽힌 판을 펼친 모양으로(`json` 요약 · `dxf` · `svg`).

    DXF 는 층으로 가른다: 외곽(구멍 포함) `OUTLINE`, 굽힘선 `BEND_UP` · `BEND_DOWN`(점선),
    「UP 90° R3」 글씨 `BEND_TEXT` — 레이저 · 절곡기 CAM 이 층으로 읽는다. 요약은 두께 · 크기 ·
    넓이 · 굽힘(선 · 각 · 안쪽 반지름 · 방향 · 굽힘 여유)과 알림(날개끼리 겹침 등).

    펼 수 없는 형상(두께가 한결같지 않음 · 솔리드 여럿)이면 400 과 까닭."""
    unfolded = services.unfold(
        payload.recipe, k_factor=payload.k_factor, flip=payload.flip, node=payload.node
    )
    if format == "json":
        return unfolded.summary()
    writer = export.write_flat_dxf if format == "dxf" else export.write_flat_svg
    media = "application/dxf" if format == "dxf" else "image/svg+xml"
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / f"flat.{format}"
        writer(unfolded, target)
        return Response(
            target.read_bytes(),
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="flat.{format}"'},
        )


@router.post("/recipe/sketch-solve")
def recipe_sketch_solve(
    payload: SketchSolveRequest, _: User = Depends(current_user)
) -> dict[str, Any]:
    """**구속 윤곽**을 풀어 본다 — 점의 자리와 남은 움직임(0 이면 다 정해졌다). 맞지 않는
    구속은 몇째인지 400 으로 말한다. 캔버스가 그린 대로가 아니라 푼 모양을 보여 준다."""
    return services.solve_sketch(payload.shape, payload.params)


@router.post("/recipe/midsurface", response_model=None)
def recipe_midsurface(
    payload: MidSurfaceRequest,
    format: str = Query(default="json", pattern="^(json|step)$"),
    _: User = Depends(current_user),
) -> Response | dict[str, Any]:
    """**중간면** — 두께가 한결같은 얇은 판의 가운데 면(셸 요소 해석용). `json` 은 판마다
    두께 · 넓이 · 면 수와 알림, `step` 은 그 면들(솔리드가 아니다 — 셸).

    판금 · 굽힌 판 · 쉘 상자 · 가져온 판금 STEP. 두께가 곳곳에 다르면(리브 · 보스) 그 자리는
    빠질 수 있고 `notes` 가 알린다. 판이 아니면 400 과 까닭."""
    mid = services.mid_surface(payload.recipe, node=payload.node)
    if format == "json":
        return dict(mid.summary())
    with tempfile.TemporaryDirectory() as folder:
        target = export.write_step(mid.shape, Path(folder) / "midsurface.step")
        return Response(
            target.read_bytes(),
            media_type="application/step",
            headers={"Content-Disposition": 'attachment; filename="midsurface.step"'},
        )


@router.post("/recipe/drawing", response_model=None)
def recipe_drawing(
    payload: DrawingRequest,
    format: str = Query(default="pdf", pattern="^(pdf|dxf|svg|png|json)$"),
    _: User = Depends(current_user),
) -> Response | dict[str, Any]:
    """**도면** — 3각법 세 뷰(정면 · 평면 · 우측면, 숨은 선 점선)에 전체 치수 · 구멍 기호와
    구멍표 · 표제란(이름 · 축척 · 재료 · 날짜). 축척은 표준 축척 중 들어가는 가장 큰 것.

    `pdf`(기본) · `dxf`(치수가 진짜 치수 객체 — CAD 에서 고친다) · `svg` · `png` ·
    `json`(축척 · 구멍표 · 치수 값). 구멍 위치는 그 구멍이 원으로 보이는 뷰의 왼쪽 아래
    모서리에서 잰다."""
    from app.core import drawing

    sheet = services.drawing_sheet(
        payload.recipe,
        title=payload.title,
        sheet=payload.sheet,
        material=payload.material,
        note=payload.note,
        node=payload.node,
    )
    if format == "json":
        summary: dict[str, Any] = sheet.summary()
        return summary
    content: bytes
    if format == "pdf":
        content, media = drawing.write_pdf(sheet), "application/pdf"
    elif format == "png":
        content, media = drawing.write_png(sheet), "image/png"
    elif format == "svg":
        content, media = drawing.write_svg(sheet).encode("utf-8"), "image/svg+xml"
    else:
        content, media = drawing.write_dxf(sheet).encode("utf-8"), "application/dxf"
    return Response(
        content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="drawing.{format}"'},
    )


@router.post("/recipe/svg")
def recipe_svg(payload: RecipeRequest, _: User = Depends(current_user)) -> Response:
    """SVG — 문서에 붙이는 2D 그림. 잘라 내는 규칙은 DXF 와 같다."""
    evaluation = services.build(payload.recipe, allow_sketch=True)
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "model.svg"
        export.write_svg(evaluation.shape, target)
        return Response(
            target.read_bytes(),
            media_type="image/svg+xml",
            headers={"Content-Disposition": 'attachment; filename="model.svg"'},
        )


# --- 진동 — 지그를 세트의 공진에 맞출 때 -----------------------------------------


@router.post("/beam-frequency")
def beam_frequency(payload: BeamRequest, _: User = Depends(current_user)) -> dict[str, Any]:
    """튜닝부(납작한 보)의 1차 굽힘 공진 **가늠값**, 또는 목표 주파수를 내는 두께.

    지그를 세트의 공진에 맞출 때 **목표 근처를 좁히는** 데 쓴다 — 해석이 아니라 닫힌 식이다.
    가정과 오차는 응답의 `accuracy` · `warnings` 에 적혀 온다."""
    try:
        if payload.target_hz is not None:
            return vibration.thickness_for_frequency(
                target_hz=payload.target_hz,
                length_mm=payload.length_mm,
                width_mm=payload.width_mm,
                material=payload.material,
                support=payload.support,
                added_mass_g=payload.added_mass_g,
            )
        if payload.thickness_mm is None:
            raise vibration.VibrationError("두께 또는 목표 주파수 중 하나를 입력하십시오.")
        return vibration.beam_frequency(
            length_mm=payload.length_mm,
            width_mm=payload.width_mm,
            thickness_mm=payload.thickness_mm,
            material=payload.material,
            support=payload.support,
            added_mass_g=payload.added_mass_g,
        )
    except vibration.VibrationError as failure:
        raise AppError(code("CAD", 12), str(failure)) from failure
