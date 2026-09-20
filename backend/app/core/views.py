"""도면 그림 — 정면 · 윗면 · 우측 · 등각을 **은선 투영**한 SVG 와 PNG.

AI 는 3D 를 못 본다. 자기가 그린 것을 확인할 길은 그림뿐이다 — 보이는 선은 실선, 가려진 선은
점선(제도 규칙). PNG 는 Claude 같은 모델이 이미지로 읽는다. 사람 화면은 three.js 가 그리므로
여기 것은 쓰지 않는다.
"""

from __future__ import annotations

import base64
import io
from typing import Any

import cairosvg
from build123d import ExportSVG, LineType, Shape

#: 시선 방향(CAD 좌표계) — 카메라가 형상에서 이쪽으로 물러나 본다. 화면의 표준 뷰와 같다.
VIEW_DIRECTIONS: dict[str, tuple[float, float, float]] = {
    "iso": (1.0, -1.0, 0.8),
    "front": (0.0, -1.0, 0.0),
    "top": (0.0, 0.0, 1.0),
    "right": (1.0, 0.0, 0.0),
}
DEFAULT_VIEWS = ("iso", "front", "top", "right")


def svg_of(shape: Shape, direction: tuple[float, float, float]) -> str:
    """한 방향의 은선 투영 SVG. 윗면은 +Y 가 위, 나머지는 +Z 가 위."""
    box = shape.bounding_box()
    center = box.center()
    span = max(box.size.X, box.size.Y, box.size.Z, 1.0)
    origin = (
        center.X + direction[0] * span * 3,
        center.Y + direction[1] * span * 3,
        center.Z + direction[2] * span * 3,
    )
    up = (0.0, 1.0, 0.0) if abs(direction[2]) > 0.99 else (0.0, 0.0, 1.0)
    visible, hidden = shape.project_to_viewport(
        origin, viewport_up=up, look_at=(center.X, center.Y, center.Z)
    )
    writer = ExportSVG(scale=1, margin=span * 0.05)
    writer.add_layer("visible", line_weight=0.35)
    writer.add_layer("hidden", line_type=LineType.ISO_DASH, line_weight=0.2)
    writer.add_shape(visible, layer="visible")
    if hidden:
        writer.add_shape(hidden, layer="hidden")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue().decode("utf-8")


def views(
    shape: Shape, names: tuple[str, ...] = DEFAULT_VIEWS, *, width: int = 640
) -> dict[str, Any]:
    """이름마다 {svg, png_base64}. 모르는 이름은 무시하지 않고 거절한다 — 오타를 조용히 넘기지
    않는다."""
    unknown = [one for one in names if one not in VIEW_DIRECTIONS]
    if unknown:
        raise ValueError(
            f"모르는 뷰입니다: {', '.join(unknown)} ({', '.join(VIEW_DIRECTIONS)})"
        )
    out: dict[str, Any] = {}
    for name in names:
        svg = svg_of(shape, VIEW_DIRECTIONS[name])
        png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=width)
        out[name] = {"svg": svg, "png_base64": base64.b64encode(png).decode("ascii")}
    return out
