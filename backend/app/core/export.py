"""6단계 — 내보내기. STEP 이 정본이고 glTF 는 화면용, STL 은 3D 프린트용이다."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Literal

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

    DOE 폴더(`write_step(names="ascii")`)만 쓴다 — 받는 쪽이 이름으로 짝지을 수 있게
    문서(해석 조건 설계 5장)가 약속한 대로 `slug` 를 붙인다. 사람이 받는 STEP 은 한글 이름
    그대로다(2026-11-18 — 깨지던 원인이 build123d 의 이중 인코딩이었다). 원본의 이름표는
    건드리지 않는다."""
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


def write_step(
    shape: Shape, path: Path, *, names: Literal["original", "ascii"] = "original"
) -> Path:
    """STEP 으로 쓴다. 이름은 둘 중 하나다:

    - `original`(사람이 받는 STEP — 작업 · 지그 내려받기): **이름표 그대로**, 한글도.
      build123d 는 이름을 OCC 에 넘길 때 UTF-8 바이트를 Latin-1 글자로 읽어 두 번 인코딩했다
      (`센서` → `ì¼ì…` — 파일에 이미 깨져 들어가 되살릴 수 없었다, 2026-11-18 원인 확인).
      그래서 그런 이름은 잠시 ASCII 자리표로 바꿔 쓰고, 다 쓴 파일에서 자리표를 표준
      이스케이프(ISO 10303-21 의 X2 · X4)로 바꾼다. 파일은 ASCII 그대로이고 CAD · OCC · 우리
      `step_import` 가 이름을 되살린다(STEP 올리기는 이름 그대로 읽는다 — `names:
      "original"`. 이미 가져온 레시피는 build123d 처럼 공백 · 괄호 · 점을 `_` 로).
    - `ascii`(DOE 폴더 — 해석 쪽과의 계약): 구성품 이름을 `topology.bodies[].step_product` 와
      같은 ASCII 로(`ascii_names`). 받는 쪽이 이 이름으로 바디를 짝짓는다.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    target = ascii_names(shape) if names == "ascii" else shape
    swapped = _placeholder_labels(target)
    try:
        if not export_step(target, path):
            raise RuntimeError(f"STEP 파일을 저장하지 못했습니다: {path.name}")
    finally:
        for node, label in swapped:
            node.label = label
    if swapped:
        text = path.read_text(encoding="ascii")
        for index, (_, label) in enumerate(swapped):
            text = text.replace(_placeholder(index), step_text(label))
        path.write_text(text, encoding="ascii")
    return path


def _placeholder(index: int) -> str:
    # 대문자 · 숫자만 — OCC 가 그대로 쓰고, STEP 의 다른 낱말과 겹치지 않을 만큼 길다.
    return f"CCSTEPNAME{index:06d}X"


def _placeholder_labels(shape: Shape) -> list[tuple[Any, str]]:
    """아스키가 아니거나 STEP 문자열에서 바꿔 써야 할 글자(`'` · `\\`)가 든 이름표를 자리표로 —
    (형상, 원래 이름) 목록. 트리 끝까지(조립 안의 조립). 쓰고 나서 되돌린다."""
    swapped: list[tuple[Any, str]] = []
    stack: list[Any] = [shape]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        label = str(getattr(node, "label", "") or "")
        if label and (not label.isascii() or "'" in label or "\\" in label):
            node.label = _placeholder(len(swapped))
            swapped.append((node, label))
        stack.extend(getattr(node, "children", ()) or ())
    return swapped


def step_text(name: str) -> str:
    """STEP 문자열 안에 쓸 이름 — `'` 는 `''`, `\\` 는 `\\\\`, 아스키 밖은 ISO 10303-21 의 표준
    이스케이프. **이어진 글자는 한 묶음**(`센서` → `\\X2\\C13CC11C\\X0\\`, BMP 밖은 `\\X4\\`) —
    글자마다 따로 쓰면 `\\X0\\\\X2\\` 처럼 역슬래시가 겹쳐 덜 꼼꼼한 리더가 `\\\\` 로
    읽을 수 있다. FreeCAD 1.0 · SpaceClaim 2025 R2 로 열어 확인했다(2026-11-18)."""
    out: list[str] = []
    run: list[int] = []
    wide = False

    def flush() -> None:
        if run:
            width, mark = (8, "X4") if wide else (4, "X2")
            out.append(f"\\{mark}\\" + "".join(f"{code:0{width}X}" for code in run) + "\\X0\\")
            run.clear()

    for char in name:
        code = ord(char)
        if code < 0x80:
            flush()
            out.append("''" if char == "'" else "\\\\" if char == "\\" else char)
            continue
        if run and wide != (code > 0xFFFF):
            flush()
        wide = code > 0xFFFF
        run.append(code)
    flush()
    return "".join(out)


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
