"""조건의 값은 **늘 mm · N · t 로 적는다** — `units.system` 은 이제 내보내기 단위계다.

전에는 조건 한 벌이 고른 계(SI 면 m · Pa)로 값을 적었다. 그러면 화면에 mm(도면 · 좌표계 ·
측정)와 m(변위량 · 하중)가 섞여 「SI 를 골랐는데 왜 mm 가 보이지」 가 됐다. 이제 입력은 도면과
같은 mm · N · t 하나이고, 점 파일을 만들 때만 고른 계로 옮긴다.

그래서 **SI 로 적혀 있던 조건은 한 번 mm · N · t 값으로 옮긴다**(내보내기 계 `si` 는 그대로
두므로 내보내는 값은 같다). 식은 `=(식)*배수` 로 감싼다. 이 파일은 그날의 규칙을 스스로 들고
있다 — 앱 코드를 부르면 나중에 코드가 바뀔 때 옛 마이그레이션이 딴 일을 한다.

Revision ID: 0022_conditions_input_mm
Revises: 0021_work_unit_system
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0022_conditions_input_mm"
down_revision = "0021_work_unit_system"
branch_labels = None
depends_on = None

_TABLES = ("work_versions", "doe_studies")

#: SI → mm · N · t 배수.
_LENGTH = 1e3
_STIFFNESS = 1e-9  # Pa/m → MPa/mm
_VELOCITY = 1e3
#: 하중 종류 → (배수, mm · N · t 의 단위 이름, SI 의 단위 이름).
_LOADS: dict[str, tuple[float, str, str]] = {
    "pressure": (1e-6, "MPa", "Pa"),
    "force": (1.0, "N", "N"),
    "moment": (1e3, "N*mm", "N*m"),
    "bearing": (1.0, "N", "N"),
    "acceleration": (1e3, "mm/s^2", "m/s^2"),
    "rotational_velocity": (1.0, "rad/s", "rad/s"),
}


def _decimal(factor: float) -> str:
    text = format(Decimal(repr(factor)), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _times(value: Any, factor: float) -> Any:
    if isinstance(value, bool) or value is None or factor == 1.0:
        return value
    if isinstance(value, int | float):
        return float(f"{value * factor:.12g}")
    if isinstance(value, str) and value.startswith("="):
        # 이미 곱해 둔 배수의 역수를 곱하면 감싼 것을 벗긴다 — 올렸다 내리면 식이 제자리.
        wrapped = re.fullmatch(r"=\((.*)\)\*([0-9.]+)", value)
        if wrapped and abs(float(wrapped.group(2)) * factor - 1.0) < 1e-9:
            return f"={wrapped.group(1)}"
        return f"=({value[1:]})*{_decimal(factor)}"
    if isinstance(value, list):
        return [_times(one, factor) for one in value]
    return value


def _move(item: dict[str, Any], key: str, factor: float) -> None:
    if key in item:
        item[key] = _times(item[key], factor)


def _convert(conditions: dict[str, Any], *, back: bool) -> dict[str, Any]:
    """SI → mm · N · t(`back=False`), 또는 그 역(`back=True`). 계와 상관없는 칸(도 · 온도 ·
    방향)은 그대로. 한 규칙으로 두 방향을 가야 올렸다 내렸다 해도 값이 제자리다."""

    def f(factor: float) -> float:
        return 1.0 / factor if back else factor

    out = json.loads(json.dumps(conditions))
    for one in out.get("constraints") or []:
        for axis in ("x", "y", "z"):
            _move(one, axis, f(_LENGTH))
        _move(one, "stiffness", f(_STIFFNESS))
    for one in out.get("loads") or []:
        kind = str(one.get("type", ""))
        if kind == "bolt_pretension":
            if one.get("unit") == ("mm" if back else "m"):
                _move(one, "preload", f(_LENGTH))
                one["unit"] = "m" if back else "mm"
            elif one.get("unit"):
                one["unit"] = "N"
        elif kind in _LOADS:
            factor, mm_name, si_name = _LOADS[kind]
            _move(one, "magnitude", f(factor))
            if one.get("unit"):
                one["unit"] = si_name if back else mm_name
    for one in out.get("contacts") or []:
        _move(one, "pinball", f(_LENGTH))
    for one in out.get("initial") or []:
        if one.get("type") == "velocity":
            _move(one, "value", f(_VELOCITY))
            _move(one, "vector", f(_VELOCITY))
    for one in out.get("mesh_hints") or []:
        _move(one, "element_size", f(_LENGTH))
        _move(one, "defeature_size", f(_LENGTH))
    return out


def to_input(conditions: dict[str, Any]) -> dict[str, Any]:
    """SI 로 적힌 한 벌 → mm · N · t 값."""
    return _convert(conditions, back=False)


def to_si(conditions: dict[str, Any]) -> dict[str, Any]:
    """mm · N · t 로 적힌 한 벌 → SI 값(되돌리기 — 옛 코드는 SI 조건의 값을 SI 로 읽는다)."""
    return _convert(conditions, back=True)


def _rewrite(convert: Any) -> None:
    connection = op.get_bind()
    for table in _TABLES:
        rows = connection.execute(
            sa.text(
                f"SELECT id, conditions FROM {table} "
                "WHERE conditions -> 'units' ->> 'system' = 'si'"
            )
        ).all()
        for row_id, conditions in rows:
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET conditions = CAST(:value AS jsonb) WHERE id = :id"
                ),
                {"value": json.dumps(convert(conditions), ensure_ascii=False), "id": row_id},
            )


def upgrade() -> None:
    _rewrite(to_input)


def downgrade() -> None:
    # **정확히 거꾸로 옮긴다.** 아무것도 안 하면 내렸다 다시 올릴 때 한 번 더 옮겨져 값이
    # 10³ 배 틀어진다. 이 사이에 새로 적은 SI 조건도 mm · N · t 로 적힌 것이라 옮기는 것이 맞다
    # (옛 코드는 SI 조건의 값을 SI 로 읽는다).
    _rewrite(to_si)
