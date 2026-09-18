"""6단계 — 내보내기. STEP 이 정본이고 glTF 는 화면용, STL 은 3D 프린트용이다."""

from __future__ import annotations

import copy
from pathlib import Path

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


def write_step(shape: Shape, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not export_step(shape, path):
        raise RuntimeError(f"STEP 을 쓰지 못했습니다: {path.name}")
    return path


def write_gltf(shape: Shape, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not export_gltf(
        shape, path, binary=True, linear_deflection=0.05, angular_deflection=0.2
    ):
        raise RuntimeError(f"glTF 를 쓰지 못했습니다: {path.name}")
    return path


def write_stl(shape: Shape, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not export_stl(shape, path):
        raise RuntimeError(f"STL 을 쓰지 못했습니다: {path.name}")
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
        raise RuntimeError("2D 로 내보낼 윤곽이 없습니다")
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
