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

import copy
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from build123d import Compound, Shape

from app.core import (
    assembly,
    export,
    features,
    geometry,
    interference,
    jig_recipe,
    planning,
    primitives,
)
from app.core.model import (
    Feature,
    FixturePlan,
    InterferenceReport,
    JigElements,
    JigResult,
    ProductGeometry,
    StageLog,
)
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


@dataclass
class JigBuild:
    """내보내기 전까지의 결과 — 미리보기는 여기서 멈춘다(파일을 쓰지 않는다)."""

    geometry: ProductGeometry
    features: list[Feature]
    plan: FixturePlan
    elements: JigElements
    jig: Compound
    product: Shape
    interference: InterferenceReport
    stages: list[StageLog]

    def preview_shape(self) -> Compound:
        """제품 + 지그 요소를 **이름표 붙은 자식**으로 — 메시가 면마다 어느 것인지 말한다."""
        children: list[Shape] = []

        def add(shape: Shape, label: str) -> None:
            child = copy.copy(shape)
            child.label = label
            children.append(child)

        add(self.product, "제품")
        add(self.elements.base_plate, "바닥" if self.plan.kind == "drop" else "바닥판")
        for i, one in enumerate(self.elements.supports, start=1):
            add(one, f"받침 {i}")
        counts = {"pin": 0, "rest": 0}
        for spec, one in zip(self.plan.locators, self.elements.locators, strict=True):
            key = "pin" if spec.kind == "pin" else "rest"
            counts[key] += 1
            add(one, f"{'위치 핀' if key == 'pin' else '받침대'} {counts[key]}")
        for i, one in enumerate(self.elements.clamps, start=1):
            add(one, f"클램프 {i}")
        for one in self.elements.others:  # 볼트 · 롤러 · 로딩 노즈 · 임팩터 — 이름표가 한국말
            add(one, one.label)
        return Compound(children=children)


def analyze(
    source: Path | Shape | dict[str, Any] | None,
    options: JigOptions,
    *,
    on_stage: OnStage | None = None,
) -> JigBuild:
    """읽기 → 특징 → 계획 → 요소 → 조립 → 간섭. **파일은 안 쓴다** — 미리보기와 실행이
    같이 쓴다."""
    clock = _Clock(on_stage)

    raw = clock.run(
        "load", lambda: resolve_product(source), lambda s: f"솔리드 {len(s.solids())}"
    )
    if options.kind == "drop":
        # 낙하는 고른 면이 아래를 보게 돌린 뒤 정규화한다 — 나머지 단계는 모른다.
        raw = geometry.pose(raw, options.drop_orientation)
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
    return JigBuild(
        geometry=geom,
        features=found,
        plan=fixture,
        elements=built,
        jig=jig,
        product=product,
        interference=report,
        stages=clock.stages,
    )


def run(
    source: Path | Shape | dict[str, Any] | None,
    options: JigOptions,
    out_dir: Path,
    *,
    basename: str = "jig",
    on_stage: OnStage | None = None,
) -> JigResult:
    made = analyze(source, options, on_stage=on_stage)
    clock = _Clock(on_stage)
    clock.stages = made.stages
    jig, product = made.jig, made.product

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
        geometry=made.geometry,
        features=made.features,
        plan=made.plan,
        elements=made.elements,
        jig=jig,
        product=product,
        interference=made.interference,
        files=files,
        stages=clock.stages,
        recipe=jig_recipe.recipe_of(made.plan, options),
    )
