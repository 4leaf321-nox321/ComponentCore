"""6단계 — 내보내기. STEP 이 정본이고 glTF 는 화면용, STL 은 3D 프린트용이다."""

from __future__ import annotations

import copy
from pathlib import Path

from build123d import Compound, Shape, export_gltf, export_step, export_stl


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
