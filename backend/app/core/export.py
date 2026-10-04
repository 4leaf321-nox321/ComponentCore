"""6단계 — 내보내기. STEP 이 정본이고 glTF 는 화면용, STL 은 3D 프린트용이다."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

from build123d import (
    Compound,
    ExportDXF,
    ExportSVG,
    Plane,
    Shape,
    Sketch,
    export_gltf,
    export_step,
    export_stl,
    section,
)


def ascii_names(shape: Shape) -> Shape:
    """조립이면 구성품 이름을 **ASCII 로 바꾼 사본** — `topology.bodies[].step_product` 와 같은
    글자.

    한글 이름은 STEP 에서 깨져(`ì¡°ë¦½`) 되살릴 수 없다. 받는 쪽이 이름으로 짝지을 수 있게
    문서(해석 조건 설계 5장)가 약속한 대로 `slug` 를 붙인다 — 2026-10-04 점검 전에는 약속만
    있고 실제로는 한글 그대로 나갔다. 원본의 이름표는 건드리지 않는다(사본의 이름만 바꾼다)."""
    from app.core.recipe.topology import _labeled_children, slug

    children = _labeled_children(shape)
    if not children:
        return shape
    renamed = []
    for index, child in enumerate(children, start=1):
        one = copy.copy(child)
        one.label = slug(str(child.label), fallback=f"body_{index}")
        renamed.append(one)
    whole = Compound(children=renamed)
    whole.label = slug(str(shape.label or ""), fallback="assembly")
    return whole


def write_step(shape: Shape, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not export_step(ascii_names(shape), path):
        raise RuntimeError(f"STEP 파일을 저장하지 못했습니다: {path.name}")
    return path


def write_gltf(shape: Shape, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not export_gltf(
        shape, path, binary=True, linear_deflection=0.05, angular_deflection=0.2
    ):
        raise RuntimeError(f"glTF 파일을 저장하지 못했습니다: {path.name}")
    return path


def write_stl(shape: Shape, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not export_stl(shape, path):
        raise RuntimeError(f"STL 파일을 저장하지 못했습니다: {path.name}")
    return path


def _flat(shape: Shape) -> Sketch:
    """2D 로 내보낼 수 있게 XY 평면에 눕힌다. 입체면 **높이 절반**에서 자른 단면을 쓴다.

    눕히지 않고 내보내면 build123d 가 「non-planar shape」 라며 좌표를 뭉갠다 — 실측."""
    flat = shape
    if not isinstance(flat, Sketch):
        box = shape.bounding_box()
        middle = (box.min.Z + box.max.Z) / 2
        flat = section(shape, section_by=Plane.XY.offset(middle))
    faces = flat.faces()
    if not faces:
        raise RuntimeError("2D로 내보낼 윤곽이 없습니다.")
    first = faces[0]
    local = Plane(origin=first.center(), z_dir=first.normal_at()).to_local_coords(flat)
    return local if isinstance(local, Sketch) else Sketch(local.wrapped)


def write_dxf(shape: Shape, path: Path) -> Path:
    """DXF — 레이저 · 워터젯 · 가공 도면이 읽는 2D 정본."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = ExportDXF()
    writer.add_shape(_flat(shape))
    writer.write(path)
    return path


def write_svg(shape: Shape, path: Path) -> Path:
    """SVG — 눈으로 보고 문서에 붙이는 2D."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = ExportSVG()
    writer.add_shape(_flat(shape))
    writer.write(path)
    return path


def combined(jig: Compound, product: Shape) -> Compound:
    """제품 + 지그 한 벌.

    **복사본으로 묶는다.** `Compound(children=…)` 는 자식을 **옮긴다** — 원본 Compound 가 비고,
    옮겨진 형상을 따로 내보내면 빈 파일이 나온다(실측: product.glb 가 240 바이트).
    """
    assembly = Compound(
        children=[copy.copy(product), *[copy.copy(child) for child in jig.children]]
    )
    assembly.label = "assembly"
    return assembly


#: 전개도 DXF 의 층 — 가공 쪽 CAM 이 층으로 가른다(외곽은 자르고 굽힘선은 표시만).
FLAT_LAYERS = {"outline": "OUTLINE", "up": "BEND_UP", "down": "BEND_DOWN", "text": "BEND_TEXT"}


def _bend_label(bend: Any) -> str:
    """「UP 90° R3」 — 가공 도면의 관례대로 영문 대문자(CAM 글꼴이 한글을 못 읽는다)."""
    radius = f" R{bend.radius:g}" if bend.radius > 0 else ""
    return f"{bend.direction.upper()} {bend.angle:.4g}°{radius}"


def write_flat_dxf(unfolded: Any, path: Path) -> Path:
    """전개도 DXF — 외곽(구멍 포함)은 `OUTLINE`, 굽힘선은 방향마다 `BEND_UP` · `BEND_DOWN`
    (점선), 굽힘마다 「UP 90° R3」 글씨는 `BEND_TEXT`. 단위는 mm."""
    from build123d import ColorIndex, Edge, LineType

    path.parent.mkdir(parents=True, exist_ok=True)
    writer = ExportDXF()
    writer.add_layer(FLAT_LAYERS["outline"], color=ColorIndex.BLACK)
    writer.add_layer(FLAT_LAYERS["up"], color=ColorIndex.RED, line_type=LineType.DASHED)
    writer.add_layer(FLAT_LAYERS["down"], color=ColorIndex.BLUE, line_type=LineType.DASHED)
    writer.add_layer(FLAT_LAYERS["text"], color=ColorIndex.GREEN)
    writer.add_shape(unfolded.face.edges(), layer=FLAT_LAYERS["outline"])
    for bend in unfolded.bends:
        line = Edge.make_line((*bend.start, 0), (*bend.end, 0))
        writer.add_shape(line, layer=FLAT_LAYERS[bend.direction])
    modelspace = writer._modelspace  # 글씨는 ezdxf 로 바로 — build123d 는 글씨를 안 쓴다
    height = max(1.5, min(5.0, unfolded.thickness * 1.5))
    for bend in unfolded.bends:
        middle = ((bend.start[0] + bend.end[0]) / 2, (bend.start[1] + bend.end[1]) / 2)
        angle = math.degrees(
            math.atan2(bend.end[1] - bend.start[1], bend.end[0] - bend.start[0])
        )
        modelspace.add_text(
            _bend_label(bend),
            height=height,
            rotation=angle,
            dxfattribs={"layer": FLAT_LAYERS["text"], "insert": (middle[0], middle[1])},
        )
    writer.write(path)
    return path


def write_flat_svg(unfolded: Any, path: Path) -> Path:
    """전개도 SVG — 눈으로 보는 것. 굽힘선은 점선(위로 빨강 · 아래로 파랑)."""
    from build123d import ColorIndex, Edge, LineType

    path.parent.mkdir(parents=True, exist_ok=True)
    writer = ExportSVG(margin=5)
    writer.add_layer(FLAT_LAYERS["outline"])
    writer.add_layer(FLAT_LAYERS["up"], line_color=ColorIndex.RED, line_type=LineType.DASHED)
    writer.add_layer(
        FLAT_LAYERS["down"], line_color=ColorIndex.BLUE, line_type=LineType.DASHED
    )
    writer.add_shape(unfolded.face, layer=FLAT_LAYERS["outline"])
    for bend in unfolded.bends:
        line = Edge.make_line((*bend.start, 0), (*bend.end, 0))
        writer.add_shape(line, layer=FLAT_LAYERS[bend.direction])
    writer.write(path)
    return path
