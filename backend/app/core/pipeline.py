"""파이프라인 — 단계를 차례로 부르고 시간을 잰다.

    제품 STEP(또는 형상 · 또는 없음)
      ▼ geometry.understand      1. Geometry Understanding
      ▼ features.recognize       2. Feature Recognition
      ▼ planning.plan            3. Fixture Planning
      ▼ assembly.build_elements  4. Support · Locator · Clamp
      ▼ assembly.assemble        5. Jig 자동 생성
      ▼ interference.check       6. 간섭 검사
      ▼ export.write_*           7. STEP (+ glTF · STL)

**여기서는 예외를 삼키지 않는다.** 어느 단계가 왜 실패했는지가 호출자(서비스)에 그대로
가야 화면이 그 말을 보여 줄 수 있다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from build123d import Shape

from app.core import assembly, export, features, geometry, interference, planning, primitives
from app.core.model import JigResult, StageLog
from app.core.options import JigOptions

T = TypeVar("T")


#: 단계가 끝날 때마다 불린다 — (이름, 걸린 ms, 한 줄 설명). 서버는 이것으로 진행을 DB 에
#: 적는다.
OnStage = Callable[[str, int, str], None]


class _Clock:
    def __init__(self, on_stage: OnStage | None) -> None:
        self.stages: list[StageLog] = []
        self._on_stage = on_stage

    def run(self, name: str, work: Callable[[], T], detail: Callable[[T], str]) -> T:
        started = time.perf_counter()
        result = work()
        stage = StageLog(
            name=name,
            millis=int((time.perf_counter() - started) * 1000),
            detail=detail(result),
        )
        self.stages.append(stage)
        if self._on_stage is not None:
            self._on_stage(stage.name, stage.millis, stage.detail)
        return result


def resolve_product(source: Path | Shape | dict[str, Any] | None) -> Shape:
    """무엇을 제품으로 삼나 — STEP 경로 · 이미 만든 형상 · 기본 도형 스펙 · 없음(시연 제품)."""
    if source is None:
        return primitives.demo_product()
    if isinstance(source, Path):
        return geometry.load_step(source)
    if isinstance(source, dict):
        return primitives.build(source)
    return source


def run(
    source: Path | Shape | dict[str, Any] | None,
    options: JigOptions,
    out_dir: Path,
    *,
    basename: str = "jig",
    on_stage: OnStage | None = None,
) -> JigResult:
    clock = _Clock(on_stage)

    raw = clock.run(
        "load", lambda: resolve_product(source), lambda s: f"솔리드 {len(s.solids())}"
    )
    geom = clock.run(
        "geometry",
        lambda: geometry.understand(raw),
        lambda g: (
            f"{g.bbox.size[0]:.1f} x {g.bbox.size[1]:.1f} x {g.bbox.size[2]:.1f} mm, "
            f"면 {g.face_count}"
        ),
    )
    found = clock.run(
        "features", lambda: features.recognize(geom), lambda f: f"특징 {len(f)} 개"
    )
    fixture = clock.run(
        "planning",
        lambda: planning.plan(geom, found, options),
        lambda p: (
            f"받침 {len(p.supports)} · 로케이터 {len(p.locators)} · 클램프 {len(p.clamps)}"
        ),
    )
    built = clock.run(
        "elements",
        lambda: assembly.build_elements(fixture, options),
        lambda e: f"부품 {len(e.all_parts())} 개",
    )
    jig = clock.run(
        "assembly", lambda: assembly.assemble(built), lambda j: f"자식 {len(j.children)}"
    )
    product = assembly.lifted_product(geom, fixture)
    report = clock.run(
        "interference",
        lambda: interference.check(built, product, options.interference_tolerance),
        lambda r: "간섭 없음" if r.ok else f"간섭 {sum(not i.ok for i in r.items)} 건",
    )

    def _export() -> dict[str, Path]:
        files = {
            "jig_step": export.write_step(jig, out_dir / f"{basename}.step"),
            "assembly_step": export.write_step(
                export.combined(jig, product), out_dir / f"{basename}-assembly.step"
            ),
        }
        if options.export_gltf:
            files["jig_glb"] = export.write_gltf(jig, out_dir / f"{basename}.glb")
            files["product_glb"] = export.write_gltf(product, out_dir / "product.glb")
        if options.export_stl:
            files["jig_stl"] = export.write_stl(jig, out_dir / f"{basename}.stl")
        return files

    files = clock.run("export", _export, lambda f: ", ".join(sorted(f)))

    return JigResult(
        geometry=geom,
        features=found,
        plan=fixture,
        elements=built,
        jig=jig,
        product=product,
        interference=report,
        files=files,
        stages=clock.stages,
    )
