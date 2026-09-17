"""CAD 작업대 — 제품 파일 없이 기본 도형을 그려 STEP · glTF 로 받는다.

지그 파이프라인과 같은 `core/primitives` 를 쓴다. 여기서 그린 도형이 곧 프로젝트의
`product_spec` 이 되므로, 화면에서 본 것과 지그가 잡는 제품이 같다.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.core import export, primitives
from app.modules.accounts.models import User
from app.modules.cad.schemas import PrimitiveInfoOut, PrimitiveKindsOut, PrimitiveRequest
from app.shared.auth import current_user
from app.shared.errors import AppError, code

router = APIRouter(prefix="/cad", tags=["cad"])

EXAMPLES: dict[str, dict[str, Any]] = {
    "box": {"kind": "box", "length": 80, "width": 50, "height": 20},
    "cylinder": {"kind": "cylinder", "radius": 25, "height": 40},
    "plate_with_holes": {
        "kind": "plate_with_holes",
        "length": 100,
        "width": 60,
        "thickness": 12,
        "hole_diameter": 8,
        "hole_margin": 10,
    },
    "bracket": {
        "kind": "bracket",
        "length": 80,
        "width": 50,
        "height": 40,
        "thickness": 8,
        "hole_diameter": 6,
    },
}


def _build(spec: dict[str, Any]) -> Any:
    try:
        return primitives.build(spec)
    except primitives.PrimitiveError as failure:
        raise AppError(code("CAD", 1), str(failure)) from failure


@router.get("/primitives", response_model=PrimitiveKindsOut)
def kinds(_: User = Depends(current_user)) -> PrimitiveKindsOut:
    return PrimitiveKindsOut(kinds=list(primitives.KINDS), examples=EXAMPLES)


@router.post("/primitives/info", response_model=PrimitiveInfoOut)
def info(payload: PrimitiveRequest, _: User = Depends(current_user)) -> PrimitiveInfoOut:
    part = _build(payload.spec)
    size = part.bounding_box().size
    return PrimitiveInfoOut(
        kind=str(payload.spec.get("kind")),
        bbox_size=(round(size.X, 3), round(size.Y, 3), round(size.Z, 3)),
        volume=round(float(part.volume), 1),
        face_count=len(part.faces()),
    )


def _render(spec: dict[str, Any], suffix: str) -> bytes:
    part = _build(spec)
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / f"primitive{suffix}"
        if suffix == ".glb":
            export.write_gltf(part, target)
        else:
            export.write_step(part, target)
        return target.read_bytes()


@router.post("/primitives/glb")
def render_glb(payload: PrimitiveRequest, _: User = Depends(current_user)) -> Response:
    """화면 미리보기용 glTF."""
    return Response(_render(payload.spec, ".glb"), media_type="model/gltf-binary")


@router.post("/primitives/step")
def render_step(payload: PrimitiveRequest, _: User = Depends(current_user)) -> Response:
    name = f"{payload.spec.get('kind', 'primitive')}.step"
    return Response(
        _render(payload.spec, ".step"),
        media_type="application/step",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
