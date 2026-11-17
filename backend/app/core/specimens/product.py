"""제품 시험 — 사용자의 제품(부품 · 작업의 형상)에 규격 시험을 건다: 정하중(IEC 62368-1
부속서 T) · 방향 하중(코드 당김 · 커넥터 렌칭) · 손잡이 · 벽걸이(IEC 62368-1 8.7 · 8.8) ·
압착(IEC 62133-2 · UN 38.3) · 적층 압축(ASTM D642, ISO 12048, ISTA) · 수압(IEC 60529) ·
비틀림 · 등가 정적 가속도(IEC 60068-2-27 · ISO 16750-3) · 정현파 진동(IEC 60068-2-6) · 랜덤
진동(IEC 60068-2-64) · 고유진동수(진동 응답 조사, ASTM E1876).

시편과 달리 형상을 새로 그리지 않는다 — **제품의 레시피를 그대로 쓴다.** 바디 이름이 같아서
제품에 붙어 있던 물성 · 파트별 설정 · 접촉이 그대로 맞는다. 더하는 것은 시험의 변수(`시험_…`),
하중 자리(정하중 — 면 나누기 하나), 구속 · 하중 · 해석 설정이다. 시험 변수는 레시피 변수라
DOE 로 하중 크기 · 누르는 자리 · 가속도 · 각도를 훑는다.

**자리**: 기본은 놓인 그대로다 — 아랫면(-Z 를 보는 바닥 면)이 받침, 정하중 · 압축은 윗면(+Z)을
위에서 누른다, 비틀림은 긴 축의 양 끝 면. 3D 에서 면을 고르면(`FacePick` — 누른 점 · 법선 ·
면 종류) 그 면이 받침 · 누를 면 · 비트는 끝이 된다. 고른 면은 「이 방향을 보는 면 중 이 점에서
가장 가까운 것」(`normal` + `near`)으로 적힌다 — 치수를 조금 바꿔도 같은 면을 다시 찾는다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.core.conditions import psd_grms
from app.core.specimens.presets import (
    G_MM,
    TESTS,
    AccelerationPreset,
    CompressionPreset,
    CrushPreset,
    DirectedPreset,
    ForcePreset,
    HandlePreset,
    ModalPreset,
    Preset,
    PressurePreset,
    RandomPreset,
    TorsionPreset,
    VibrationPreset,
    VibrationSetup,
)

#: 시험이 더하는 변수 · 노드 · 태그의 머리말 — 제품의 이름과 겹치지 않게.
PREFIX = "시험_"
#: kg → N.
G = 9.80665
#: 시험이 쓰는 선택 그룹의 이름 — 모두 「시험 」 으로 시작한다(서버가 그것으로 가린다).
SUPPORT = "시험 받침면"
PATCH = "시험 하중 자리"
PRESSED = "시험 누름면"
HOLD = "시험 고정 자리"
FIXED_END = "시험 고정 끝"
TWISTED_END = "시험 비트는 끝"
LOADED = "시험 하중면"
WET = "시험 수압면"
NAMES = (SUPPORT, PATCH, PRESSED, HOLD, FIXED_END, TWISTED_END, LOADED, WET)
#: 물 1 m 의 압력(MPa) — 밀도 x g x 깊이 = 1000 kg/m³ x 9.80665 m/s² x 1 m = 9806.65 Pa.
WATER_MPA_PER_M = 0.00980665
PATCH_TAG = "시험_하중_자리"
AXES = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}
#: 고를 수 있는 자리 — 화면의 이름.
SLOTS = {"support": "고정 면", "load": "하중 면", "twist": "비트는 끝 면"}
#: 시험마다 고를 수 있는 자리.
FACE_SLOTS: dict[str, tuple[str, ...]] = {
    "force": ("load", "support"),
    "directed": ("load", "support"),
    "handle": ("support",),
    "crush": ("load", "support"),
    "compression": (),
    "pressure": ("load", "support"),
    "torsion": ("support", "twist"),
    "acceleration": ("support",),
    "vibration": ("support",),
    "random": ("support",),
    "modal": ("support",),
}
#: 자리를 못 찾았을 때 사람에게 하는 말.
HINT = (
    "3D에서 면을 다시 고르거나, 기본 자리(아랫면: -Z를 향하는 평면, 윗면: +Z를 향하는 "
    "평면, 비틀림: 긴 축 양 끝의 평면)가 있도록 제품을 돌려 놓고 다시 적용하십시오."
)
#: 제품의 조건에서 가져오는 것 — 구속 · 하중 · 초기조건 · 해석 설정은 시험의 것으로 바꾼다.
KEPT = (
    "units",
    "named_selections",
    "materials",
    "contacts",
    "body_settings",
    "mesh_hints",
    "coordinate_systems",
)


class ProductTestError(ValueError):
    """사람이 고칠 수 있는 실패 — 메시지가 그대로 화면에 간다."""


#: 변위 일정 구간을 나눌 때 이웃 행의 주파수 비 상한 — 1/12 옥타브. 행 사이를 직선으로 이으면
#: f² 를 많아야 ((r - 1) / (r + 1))² ≈ 0.08 % 크게 읽는다(1/6 옥타브면 0.3 %, 1 옥타브면 11 % —
#: SimEngBay 가 1/12 옥타브 이하를 부탁했다, 2026-11-17).
SWEEP_STEP = 2 ** (1 / 12)


def sweep_table(setup: VibrationSetup) -> list[list[float]] | None:
    """정현파 스윕의 **주파수별 배율** — 가속도 진폭(`acceleration_g`)에 곱하는 값.

    교차 주파수 f_c 아래는 변위가 일정하므로 가속도가 (2πf)² · d = a · (f / f_c)² 이다.
    조건의 배율 표는 행 사이를 직선으로 이으므로 그 곡선을 로그 간격(이웃 비 ≤
    `SWEEP_STEP`)의 행으로 나눈다. f_c 위는 1 이다. 첫 행 · 끝 행은 시험 범위의 끝
    그대로(표가 범위를 다 덮어야 한다). 변위가 없거나 f_c 가 시험 범위 아래면 `None` —
    배율 표가 필요 없다."""
    crossover = setup.crossover
    if crossover is None or crossover <= setup.freq_min:
        return None
    top = min(crossover, setup.freq_max)
    steps = max(1, math.ceil(math.log(top / setup.freq_min) / math.log(SWEEP_STEP)))
    rows: list[list[float]] = []
    for step in range(steps + 1):
        if step == 0:
            frequency = setup.freq_min
        elif step == steps:
            frequency = top if top == setup.freq_max else round(top, 3)
        else:
            frequency = round(setup.freq_min * (top / setup.freq_min) ** (step / steps), 3)
        if rows and frequency <= rows[-1][0]:
            continue
        rows.append([frequency, round(min(1.0, (frequency / crossover) ** 2), 6)])
    if top < setup.freq_max:
        rows[-1][1] = 1.0
        rows.append([setup.freq_max, 1.0])
    return rows


#: 축을 하나씩 거는 시험의 안내 — 한 조건의 가진은 동시라 축 셋을 한 조건에 넣지 않는다.
_OTHER_AXES = (
    "다른 축은 DOE 의 「조건 변경」 에서 하중 「{load}」 · 방향을 X · Y · Z 로 고르면 "
    "설계점마다 한 축씩 나뉩니다(한 조건에 축을 여럿 넣으면 동시에 흔든 것으로 합산됩니다)."
)


def _shaking(axis: str) -> list[int]:
    direction = AXES.get(axis.lower())
    if direction is None:
        raise ProductTestError(f"진동 방향은 X, Y, Z 중 하나여야 합니다: {axis}")
    return direction


@dataclass(frozen=True)
class FacePick:
    """3D 에서 고른 면 — 누른 점, 그 자리의 법선, 면 종류(plane · cylinder …)."""

    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    kind: str = "plane"


@dataclass
class ProductTest:
    recipe: dict[str, Any]
    conditions: dict[str, Any]
    notes: list[str] = field(default_factory=list)
    ends: dict[str, tuple[int, float]] = field(default_factory=dict)
    """기본 자리로 고른 끝 면이 **정말 끝에 있어야 하는** 선택 그룹 → (축 번호, 좌표). 끝이
    둥근 제품이면 「그 방향을 보는 가장 가까운 평면」 이 안쪽의 엉뚱한 면일 수 있다 — 서버가
    풀어 본 중심으로 확인한다."""


def _result_id(recipe: dict[str, Any]) -> str:
    if recipe.get("result"):
        return str(recipe["result"])
    nodes = recipe.get("nodes") or []
    if not nodes:
        raise ProductTestError("제품에 형상이 없습니다.")
    return str(nodes[-1]["id"])


def _check_names(recipe: dict[str, Any], conditions: dict[str, Any]) -> None:
    """시험이 쓰는 이름이 제품에 이미 있으면 막는다 — 조용히 덮으면 제품의 치수가 바뀐다."""
    params = set((recipe.get("params") or {}).keys())
    ids = {str(one.get("id")) for one in recipe.get("nodes") or [] if isinstance(one, dict)}
    taken = sorted(name for name in params | ids if name.startswith(PREFIX))
    selections = {str(one.get("name")) for one in conditions.get("named_selections") or []}
    taken += sorted(selections & set(NAMES))
    if taken:
        raise ProductTestError(
            f"제품에 시험이 쓰는 이름이 이미 있습니다: {', '.join(taken)}. 이미 시험을 건 "
            "작업이면 원래 제품에서 다시 거십시오."
        )


def _unit(vector: tuple[float, float, float]) -> list[float]:
    size = math.sqrt(sum(one * one for one in vector))
    if size < 1e-9:
        raise ProductTestError("고른 면의 법선이 없습니다. 면을 다시 고르십시오.")
    return [round(one / size, 4) for one in vector]


def _one_face(pick: FacePick) -> dict[str, Any]:
    point = [round(float(one), 4) for one in pick.point]
    if pick.kind == "plane":
        return {"what": "faces", "normal": _unit(pick.normal), "near": point}
    return {"what": "faces", "kind": pick.kind, "near": point}


def picked(picks: list[FacePick]) -> dict[str, Any]:
    """고른 면들의 선택 — 하나면 그 면, 여럿이면 `any`."""
    if len(picks) == 1:
        return _one_face(picks[0])
    return {"any": [_one_face(one) for one in picks]}


def _face(name: str, select: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "entity": "face", "select": select}


def apply(
    preset: Preset,
    recipe: dict[str, Any],
    conditions: dict[str, Any] | None,
    *,
    bbox: tuple[list[float], list[float]],
    point: tuple[float | None, ...] | None = None,
    axis: str | None = None,
    faces: dict[str, list[FacePick]] | None = None,
    mass: float | None = None,
    direction: tuple[float, float, float] | None = None,
) -> ProductTest:
    """제품 레시피 · 조건에 시험을 더한 새 한 벌.

    `bbox` 는 제품의 경계 상자(서버가 만들어 본 것), `point` 는 정하중을 누르는 자리(X, Y[, Z]
    — 빈 칸은 고른 점이나 윗면 가운데), `axis` 는 진동(정현파 · 랜덤) · 비틀림 축(비우면
    진동 Z, 비틀림은 가장 긴 축, 등가 가속도는 Z), `faces` 는 3D 에서 고른
    자리(`FACE_SLOTS`), `mass` 는 적층 압축의 제품 무게(kg), `direction` 은 방향 하중의
    방향(비우면 고른 면에서 바깥으로)."""
    if preset.test not in FACE_SLOTS:
        raise ProductTestError(f"‘{preset.name}’은(는) 제품에 거는 시험이 아닙니다.")
    given = dict(conditions or {})
    _check_names(recipe, given)
    chosen = {slot: list(picks) for slot, picks in (faces or {}).items() if picks}
    allowed = FACE_SLOTS[preset.test]
    for slot in chosen:
        if slot not in allowed:
            raise ProductTestError(
                f"{TESTS[preset.test]} 시험에는 ‘{SLOTS.get(slot, slot)}’을(를) 고르지 "
                "않습니다."
            )
    made = {
        **recipe,
        "params": dict(recipe.get("params") or {}),
        "nodes": list(recipe["nodes"]),
    }
    kept = {key: given[key] for key in KEPT if given.get(key)}
    selections = list(kept.get("named_selections") or [])
    notes: list[str] = []
    materials = kept.get("materials") or []
    notes.append(
        f"제품에 지정된 물성 {len(materials)}개를 그대로 사용합니다."
        if materials
        else "제품에 물성이 없습니다. 해석 조건에서 물성을 지정하십시오."
    )
    if any(given.get(key) for key in ("constraints", "loads", "initial")):
        notes.append("제품의 기존 구속, 하중, 초기조건은 이 시험의 것으로 바꿨습니다.")
    if not preset.verified:
        notes.append(
            f"규격값을 아직 규격서와 대조하지 않았습니다(출처: {preset.source or '없음'})."
        )
    test = _Test(made, selections, notes, bbox, chosen)
    if isinstance(preset, ForcePreset):
        rules = test.force(preset, point)
    elif isinstance(preset, HandlePreset):
        rules = test.handle(preset)
    elif isinstance(preset, CompressionPreset):
        rules = test.compression(preset, mass)
    elif isinstance(preset, TorsionPreset):
        rules = test.torsion(preset, axis)
    elif isinstance(preset, VibrationPreset):
        rules = test.vibration(preset, axis or "z")
    elif isinstance(preset, RandomPreset):
        rules = test.random(preset, axis or "z")
    elif isinstance(preset, CrushPreset):
        rules = test.crush(preset)
    elif isinstance(preset, PressurePreset):
        rules = test.pressure(preset)
    elif isinstance(preset, AccelerationPreset):
        rules = test.acceleration(preset, axis or "z")
    elif isinstance(preset, DirectedPreset):
        rules = test.directed(preset, direction)
    else:
        assert isinstance(preset, ModalPreset)
        rules = test.modal(preset)
    out = {"schema_version": 1, **kept, "named_selections": selections, **rules}
    return ProductTest(recipe=made, conditions=out, notes=notes, ends=test.ends)


class _Test:
    """시험 한 벌을 만드는 동안의 상태 — 레시피 · 선택 그룹 · 메모에 더해 간다."""

    def __init__(
        self,
        made: dict[str, Any],
        selections: list[dict[str, Any]],
        notes: list[str],
        bbox: tuple[list[float], list[float]],
        faces: dict[str, list[FacePick]],
    ) -> None:
        self.made = made
        self.selections = selections
        self.notes = notes
        self.low, self.high = bbox
        self.faces = faces
        self.ends: dict[str, tuple[int, float]] = {}

    def support(self, name: str = SUPPORT, role: str = "bottom") -> str:
        """받침 — 고른 면, 아니면 아랫면(`role`). 선택 그룹 이름을 돌려준다."""
        picks = self.faces.get("support")
        if picks:
            self.selections.append(_face(name, picked(picks)))
            self.notes.append(f"고른 면 {len(picks)}개를 고정합니다.")
        else:
            self.selections.append(_face(name, {"what": "faces", "role": role}))
            where = (
                "아랫면(-Z를 향하는 평면)" if role == "bottom" else "윗면(+Z를 향하는 평면)"
            )
            self.notes.append(f"받침은 제품의 {where}입니다.")
        return name

    def opposite(self, normal: list[float]) -> str:
        """누르는 면의 반대쪽 받침 — 고른 받침이 있으면 그것, 위아래로 누르면 아랫면 · 윗면,
        옆으로 누르면 그 반대쪽 끝의 평면(끝에 있는지는 서버가 확인한다 — `ends`)."""
        if self.faces.get("support") or abs(normal[2]) > 0.9:
            return self.support(role="top" if normal[2] < -0.9 else "bottom")
        index = max(range(3), key=lambda one: abs(normal[one]))
        at = self.low[index] if normal[index] > 0 else self.high[index]
        spot = [
            round((low + high) / 2, 4) for low, high in zip(self.low, self.high, strict=True)
        ]
        spot[index] = round(at, 4)
        back = [-one + 0.0 for one in normal]
        self.selections.append(_face(SUPPORT, {"what": "faces", "normal": back, "near": spot}))
        if abs(normal[index]) > 0.99:
            self.ends[SUPPORT] = (index, at)
        self.notes.append("받침은 누르는 면의 반대쪽 끝 면입니다.")
        return SUPPORT

    def force(
        self, preset: ForcePreset, point: tuple[float | None, ...] | None
    ) -> dict[str, Any]:
        px, py, pz = [*list(point or ()), None, None, None][:3]
        load = self.faces.get("load") or []
        if len(load) > 1:
            raise ProductTestError("누를 면은 하나만 고르십시오.")
        if load and load[0].kind != "plane":
            raise ProductTestError(
                "누를 면은 평면이어야 합니다. 곡면은 아직 하중 자리로 나눌 수 없습니다."
            )
        normal = _unit(load[0].normal) if load else [0.0, 0.0, 1.0]
        base = (
            list(load[0].point)
            if load
            else [
                (self.low[0] + self.high[0]) / 2,
                (self.low[1] + self.high[1]) / 2,
                self.high[2],
            ]
        )
        x, y, z = (
            round(float(given if given is not None else default), 4)
            for given, default in zip((px, py, pz), base, strict=True)
        )
        params = self.made["params"]
        params.update(
            {
                f"{PREFIX}하중": preset.setup.force,
                f"{PREFIX}지름": preset.setup.probe_diameter,
                f"{PREFIX}X": x,
                f"{PREFIX}Y": y,
            }
        )
        if load:
            params[f"{PREFIX}Z"] = z
            spot: list[Any] = [f"={PREFIX}X", f"={PREFIX}Y", f"={PREFIX}Z"]
            on: dict[str, Any] = {"normal": normal, "near": spot}
        else:
            spot = [f"={PREFIX}X", f"={PREFIX}Y", round(self.high[2], 4)]
            on = {"role": "top", "near": spot}
        result = _result_id(self.made)
        self.made["nodes"].append(
            {
                "id": f"{PREFIX}하중_자리",
                "op": "divide_face",
                "label": "하중 자리",
                "target": result,
                "on": on,
                "shape": "circle",
                "radius": f"={PREFIX}지름 / 2",
                "at": spot,
                "tag": PATCH_TAG,
            }
        )
        if self.made.get("result"):
            self.made["result"] = f"{PREFIX}하중_자리"
        self.selections.append(_face(PATCH, {"what": "faces", "tag": PATCH_TAG}))
        # 아랫면을 누르면 받침은 윗면이다 — 같은 면을 누르고 받칠 수는 없다.
        support = self.support(role="top" if normal[2] < -0.9 else "bottom")
        where = "고른 면" if load else "윗면"
        coordinates = f"({x:g}, {y:g}, {z:g})" if load else f"({x:g}, {y:g})"
        self.notes.append(
            f"{where}의 {coordinates} 자리를 지름 {preset.setup.probe_diameter:g} mm 원으로 "
            f"{preset.setup.force:g} N 누릅니다. 누르는 자리는 변수 ‘{PREFIX}X’·‘{PREFIX}Y’"
            f"{'·‘' + PREFIX + 'Z’' if load else ''}로 바꿀 수 있습니다."
        )
        return {
            "constraints": [{"name": "받침 고정", "type": "fixed_support", "on": support}],
            "loads": [
                {
                    "name": f"정하중 {preset.setup.force:g} N",
                    "type": "force",
                    "on": PATCH,
                    "magnitude": f"={PREFIX}하중",
                    "direction": [-one + 0.0 for one in normal],
                }
            ],
            "analysis": {
                "type": "static",
                "large_deflection": preset.analysis.large_deflection,
            },
        }

    def handle(self, preset: HandlePreset) -> dict[str, Any]:
        if not self.faces.get("support"):
            raise ProductTestError(
                "손잡이·벽걸이 시험은 고정할 자리(손잡이를 잡는 면, 벽걸이 브래킷이 닿는 "
                "면)를 3D에서 골라야 합니다."
            )
        factor = preset.setup.weight_factor
        self.made["params"][f"{PREFIX}배수"] = factor
        hold = self.support(HOLD)
        self.notes.append(
            f"제품 전체에 무게의 {factor:g}배가 아래(-Z)로 걸리게 위로 {factor:g} g 가속합니다"
            "(관성력이 아래로 작용 — 밀도가 무게를 정합니다). 손잡이가 여럿이면 모두 고르면 "
            "하중이 나뉩니다."
        )
        return {
            "constraints": [{"name": "고정 자리", "type": "fixed_support", "on": hold}],
            "loads": [
                {
                    "name": f"무게 {factor:g}배",
                    "type": "acceleration",
                    "magnitude": f"={PREFIX}배수 * {G_MM}",
                    "direction": [0, 0, 1],
                }
            ],
            "analysis": {
                "type": "static",
                "large_deflection": preset.analysis.large_deflection,
            },
        }

    def compression(self, preset: CompressionPreset, mass: float | None) -> dict[str, Any]:
        if mass is None or mass <= 0:
            raise ProductTestError("적층 압축 시험에는 제품 무게(kg)가 필요합니다.")
        setup = preset.setup
        params = self.made["params"]
        params[f"{PREFIX}무게"] = mass
        params[f"{PREFIX}계수"] = setup.factor
        if setup.layers is not None:
            params[f"{PREFIX}단수"] = setup.layers
            params[f"{PREFIX}하중"] = (
                f"={PREFIX}무게 * {G} * ({PREFIX}단수 - 1) * {PREFIX}계수"
            )
            load = mass * G * (setup.layers - 1) * setup.factor
            how = f"{setup.layers}단 적재"
        else:
            assert setup.stack_height is not None
            height = round(self.high[2] - self.low[2], 4)
            if setup.stack_height <= height:
                raise ProductTestError(
                    f"적재 높이({setup.stack_height:g} mm)가 제품 높이({height:g} mm)보다 "
                    "높아야 합니다."
                )
            params[f"{PREFIX}적재_높이"] = setup.stack_height
            params[f"{PREFIX}제품_높이"] = height
            params[f"{PREFIX}하중"] = (
                f"={PREFIX}무게 * {G} * ({PREFIX}적재_높이 - {PREFIX}제품_높이) "
                f"/ {PREFIX}제품_높이 * {PREFIX}계수"
            )
            load = mass * G * (setup.stack_height - height) / height * setup.factor
            how = f"적재 높이 {setup.stack_height:g} mm(제품 높이 {height:g} mm)"
        support = self.support()
        self.selections.append(_face(PRESSED, {"what": "faces", "role": "top"}))
        self.notes.append(
            f"{how}, 무게 {mass:g} kg, 계수 {setup.factor:g}: 윗면 전체를 {load:.4g} N으로 "
            "누릅니다. 무게는 변수 ‘시험_무게’로 바꿀 수 있습니다."
        )
        return {
            "constraints": [{"name": "받침 고정", "type": "fixed_support", "on": support}],
            "loads": [
                {
                    "name": "적층 하중",
                    "type": "force",
                    "on": PRESSED,
                    "magnitude": f"={PREFIX}하중",
                    "direction": [0, 0, -1],
                }
            ],
            "analysis": {
                "type": "static",
                "large_deflection": preset.analysis.large_deflection,
            },
        }

    def torsion(self, preset: TorsionPreset, axis: str | None) -> dict[str, Any]:
        sizes = [high - low for low, high in zip(self.low, self.high, strict=True)]
        name = (axis or "xyz"[sizes.index(max(sizes))]).lower()
        if name not in AXES:
            raise ProductTestError(f"비틀림 축은 X, Y, Z 중 하나여야 합니다: {axis}")
        index = "xyz".index(name)
        direction = AXES[name]
        center = [(low + high) / 2 for low, high in zip(self.low, self.high, strict=True)]

        def end(slot: str, label: str, sign: int, at: float) -> None:
            picks = self.faces.get(slot)
            if picks:
                self.selections.append(_face(label, picked(picks)))
                return
            spot = [round(one, 4) for one in center]
            spot[index] = round(at, 4)
            normal = [sign * one for one in direction]
            self.selections.append(
                _face(label, {"what": "faces", "normal": normal, "near": spot})
            )
            self.ends[label] = (index, at)

        end("support", FIXED_END, -1, self.low[index])
        end("twist", TWISTED_END, 1, self.high[index])
        self.made["params"][f"{PREFIX}각도"] = preset.setup.angle
        moved: dict[str, Any] = {key: 0 for key in ("x", "y", "z", "rx", "ry", "rz")}
        moved[name] = None  # 축 방향으로는 자유 — 비틀면 짧아진다
        moved[f"r{name}"] = f"={PREFIX}각도"
        where = {0: "고른 면", 1: "고른 면과 반대쪽 끝의 평면", 2: "긴 축 양 끝의 평면"}
        self.notes.append(
            f"{name.upper()}축의 한쪽 끝을 고정하고 다른 끝을 {preset.setup.angle:g}° "
            f"비틉니다(각도는 변수 ‘{PREFIX}각도’). 끝 면은 {where[len(self.ends)]}입니다."
        )
        return {
            "constraints": [
                {"name": "끝 고정", "type": "fixed_support", "on": FIXED_END},
                {
                    "name": "끝 비틀기",
                    "type": "remote_displacement",
                    "on": TWISTED_END,
                    "behavior": "rigid",
                    **moved,
                },
            ],
            "loads": [],
            "analysis": {
                "type": "static",
                "large_deflection": preset.analysis.large_deflection,
            },
        }

    def vibration(self, preset: VibrationPreset, axis: str) -> dict[str, Any]:
        direction = _shaking(axis)
        setup = preset.setup
        self.made["params"].update(
            {
                f"{PREFIX}가속도_g": setup.acceleration_g,
                f"{PREFIX}가속도": f"={PREFIX}가속도_g * {G_MM}",
            }
        )
        support = self.support()
        table = sweep_table(setup)
        span = f"{setup.freq_min:g}~{setup.freq_max:g} Hz"
        crossover = setup.crossover
        if crossover is None:
            level = f"{setup.acceleration_g:g} g 를 {span} 에서 훑습니다"
        elif table is None:
            level = (
                f"{setup.acceleration_g:g} g 를 {span} 에서 훑습니다(교차 주파수 "
                f"{crossover:.1f} Hz 가 범위 아래라 변위 일정 구간이 없습니다)"
            )
        elif crossover >= setup.freq_max:
            peak = setup.acceleration_g * (setup.freq_max / crossover) ** 2
            level = (
                f"변위 {setup.displacement_mm:g} mm 를 {span} 에서 훑습니다(범위 전체가 교차 "
                f"주파수 {crossover:.1f} Hz 아래 — 가속도는 {setup.freq_max:g} Hz 에서 최대 "
                f"{peak:.3g} g)"
            )
        else:
            level = (
                f"{span} 를 훑습니다. 교차 주파수 {crossover:.1f} Hz 아래는 변위 "
                f"{setup.displacement_mm:g} mm 일정(가속도 = (2πf)² x 변위 — 주파수별 배율 "
                f"표), 위는 {setup.acceleration_g:g} g 일정입니다"
            )
        self.notes.append(
            f"받침을 가진대에 고정하고 {axis.upper()}축으로 {level}(감쇠비 "
            f"{setup.damping_ratio:g}). {_OTHER_AXES.format(load='가진')}"
        )
        if table is not None:
            self.notes.append(
                f"변수 ‘{PREFIX}가속도_g’ 를 바꾸면 변위 구간도 같은 비로 바뀝니다(교차 "
                "주파수는 그대로). 변위만 바꾸려면 규격을 고쳐 다시 적용하십시오."
            )
        load: dict[str, Any] = {
            "name": "가진",
            "type": "acceleration",
            "magnitude": f"={PREFIX}가속도",
            "direction": direction,
        }
        if table is not None:
            load["frequency_table"] = table
        return {
            "constraints": [{"name": "가진대 고정", "type": "fixed_support", "on": support}],
            "loads": [load],
            "analysis": {
                "type": "harmonic",
                "frequency_range": [setup.freq_min, setup.freq_max],
                "solution_intervals": setup.points,
                "method": "mode_superposition",
                "modes": setup.modes,
                "damping_ratio": setup.damping_ratio,
            },
        }

    def random(self, preset: RandomPreset, axis: str) -> dict[str, Any]:
        direction = _shaking(axis)
        setup = preset.setup
        table = [[frequency, value] for frequency, value in setup.psd]
        grms = psd_grms(table) or 0.0
        low, high = table[0][0], table[-1][0]
        support = self.support()
        self.notes.append(
            f"받침을 가진대에 고정하고 {axis.upper()}축으로 가속도 PSD {low:g}~{high:g} Hz"
            f"(Grms {grms:.2f} g)를 겁니다(감쇠비 {setup.damping_ratio:g}). "
            f"{_OTHER_AXES.format(load='랜덤 가진')}"
        )
        self.notes.append(
            f"모드 {setup.modes}개로 모드 중첩을 합니다. 모드가 PSD 최고 주파수의 1.5배"
            f"({1.5 * high:g} Hz)까지 덮지 못하면 응답이 작게 나오니 모드 수를 늘리십시오."
        )
        return {
            "constraints": [{"name": "가진대 고정", "type": "fixed_support", "on": support}],
            "loads": [
                {
                    "name": "랜덤 가진",
                    "type": "psd_acceleration",
                    "direction": direction,
                    "psd_table": table,
                }
            ],
            "analysis": {
                "type": "random",
                "modes": setup.modes,
                "damping_ratio": setup.damping_ratio,
            },
        }

    def crush(self, preset: CrushPreset) -> dict[str, Any]:
        load = self.faces.get("load") or []
        if any(one.kind != "plane" for one in load):
            raise ProductTestError("누를 면은 평면이어야 합니다(평판으로 누릅니다).")
        normal = _unit(load[0].normal) if load else [0.0, 0.0, 1.0]
        pressed = picked(load) if load else {"what": "faces", "role": "top"}
        force = preset.setup.force
        self.made["params"][f"{PREFIX}힘"] = force
        self.selections.append(_face(PRESSED, pressed))
        support = self.opposite(normal)
        self.notes.append(
            f"{'고른 면을' if load else '윗면 전체를'} 평판으로 {force:g} N 누릅니다(힘은 "
            f"변수 ‘{PREFIX}힘’)."
        )
        return {
            "constraints": [{"name": "받침 고정", "type": "fixed_support", "on": support}],
            "loads": [
                {
                    "name": f"압착 {force:g} N",
                    "type": "force",
                    "on": PRESSED,
                    "magnitude": f"={PREFIX}힘",
                    "direction": [-one + 0.0 for one in normal],
                }
            ],
            "analysis": {
                "type": "static",
                "large_deflection": preset.analysis.large_deflection,
            },
        }

    def pressure(self, preset: PressurePreset) -> dict[str, Any]:
        setup = preset.setup
        params = self.made["params"]
        params[f"{PREFIX}수심"] = setup.depth
        params[f"{PREFIX}계수"] = setup.factor
        params[f"{PREFIX}수압"] = f"={PREFIX}수심 * {WATER_MPA_PER_M} * {PREFIX}계수"
        load = self.faces.get("load") or []
        self.selections.append(_face(WET, picked(load) if load else {"what": "faces"}))
        support = self.support()
        value = setup.depth * WATER_MPA_PER_M * setup.factor
        self.notes.append(
            f"수심 {setup.depth:g} m(계수 {setup.factor:g})의 수압 {value * 1000:.4g} kPa를 "
            f"{'고른 면' if load else '모든 면'}에 고르게 겁니다. 수압은 스스로 평형이라 "
            "받침은 강체 운동만 막습니다(받침 면은 변형하지 않으니 보려는 면을 받침으로 "
            "고르지 마십시오)."
        )
        if not load:
            self.notes.append(
                "속이 빈 제품(안쪽 면)이나 조립(맞닿은 면)이면 바깥 면만 3D에서 고르십시오."
            )
        return {
            "constraints": [{"name": "받침 고정", "type": "fixed_support", "on": support}],
            "loads": [
                {
                    "name": f"수압 {setup.depth:g} m",
                    "type": "pressure",
                    "on": WET,
                    "magnitude": f"={PREFIX}수압",
                    "direction": "normal",
                }
            ],
            "analysis": {
                "type": "static",
                "large_deflection": preset.analysis.large_deflection,
            },
        }

    def acceleration(self, preset: AccelerationPreset, axis: str) -> dict[str, Any]:
        direction = AXES.get(axis.lower())
        if direction is None:
            raise ProductTestError(f"가속 방향은 X, Y, Z 중 하나여야 합니다: {axis}")
        setup = preset.setup
        self.made["params"].update(
            {
                f"{PREFIX}가속도_g": setup.acceleration_g,
                f"{PREFIX}배수": setup.factor,
                f"{PREFIX}가속도": f"={PREFIX}가속도_g * {PREFIX}배수 * {G_MM}",
            }
        )
        support = self.support()
        pulse = f", {setup.duration_ms:g} ms" if setup.duration_ms else ""
        self.notes.append(
            f"충격({setup.acceleration_g:g} g{pulse})을 정적 가속도 "
            f"{setup.acceleration_g * setup.factor:g} g(배율 {setup.factor:g})로 근사합니다 — "
            f"{axis.upper()}축 +방향으로 가속하므로 관성력은 -방향입니다. 반대 방향은 응력의 "
            "부호만 바뀝니다(선형). 실제 충격 응답은 고유진동수와 지속 시간에 따라 다르니 "
            "고유진동수를 함께 확인하십시오."
        )
        return {
            "constraints": [{"name": "받침 고정", "type": "fixed_support", "on": support}],
            "loads": [
                {
                    "name": "가속도",
                    "type": "acceleration",
                    "magnitude": f"={PREFIX}가속도",
                    "direction": direction,
                }
            ],
            "analysis": {
                "type": "static",
                "large_deflection": preset.analysis.large_deflection,
            },
        }

    def directed(
        self, preset: DirectedPreset, direction: tuple[float, float, float] | None
    ) -> dict[str, Any]:
        load = self.faces.get("load") or []
        if not load:
            raise ProductTestError(
                "방향 하중은 힘을 걸 면(코드 고정부, 커넥터 등)을 3D에서 골라야 합니다."
            )
        if direction is not None:
            way = _unit(direction)
        elif load[0].kind == "plane":
            way = _unit(load[0].normal)  # 고른 면에서 바깥으로 — 당긴다
        else:
            raise ProductTestError("곡면을 골랐으면 하중의 방향을 정하십시오.")
        setup = preset.setup
        self.selections.append(_face(LOADED, picked(load)))
        support = self.support()
        loads: list[dict[str, Any]] = []
        said = []
        if setup.force is not None:
            self.made["params"][f"{PREFIX}힘"] = setup.force
            loads.append(
                {
                    "name": f"힘 {setup.force:g} N",
                    "type": "force",
                    "on": LOADED,
                    "magnitude": f"={PREFIX}힘",
                    "direction": way,
                }
            )
            said.append(f"힘 {setup.force:g} N")
        if setup.torque is not None:
            self.made["params"][f"{PREFIX}토크"] = setup.torque
            loads.append(
                {
                    "name": f"모멘트 {setup.torque:g} N·m",
                    "type": "moment",
                    "on": LOADED,
                    "magnitude": f"={PREFIX}토크 * 1000",
                    "direction": way,
                }
            )
            said.append(f"모멘트 {setup.torque:g} N·m(그 축을 도는 오른손 방향)")
        shown = ", ".join(f"{one:g}" for one in way)
        names = " · ".join(
            f"‘{PREFIX}{name}’"
            for name, value in (("힘", setup.force), ("토크", setup.torque))
            if value is not None
        )
        self.notes.append(
            f"고른 면 {len(load)}개에 방향 ({shown})으로 {' · '.join(said)}를 겁니다. 크기는 "
            f"변수 {names}로 바꿀 수 있습니다."
        )
        return {
            "constraints": [{"name": "받침 고정", "type": "fixed_support", "on": support}],
            "loads": loads,
            "analysis": {
                "type": "static",
                "large_deflection": preset.analysis.large_deflection,
            },
        }

    def modal(self, preset: ModalPreset) -> dict[str, Any]:
        setup = preset.setup
        analysis: dict[str, Any] = {"type": "modal", "modes": setup.modes}
        if setup.freq_max is not None:
            analysis["frequency_range"] = [setup.freq_min, setup.freq_max]
            span = f"{setup.freq_min:g}~{setup.freq_max:g} Hz 안의 모드를 최대 {setup.modes}개"
        else:
            span = f"낮은 차수부터 모드 {setup.modes}개를"
        if setup.support == "free":
            if self.faces.get("support"):
                raise ProductTestError("자유-자유 시험에는 고정 면을 고르지 않습니다.")
            if setup.freq_max is None:
                analysis["modes"] = setup.modes + 6
                span = f"강체 모드 6개를 더해 모드 {setup.modes + 6}개를"
            self.notes.append(
                f"구속 없이(자유-자유) {span} 구합니다. 처음 6개는 0 Hz 근처의 강체 "
                "모드입니다."
            )
            return {"constraints": [], "loads": [], "analysis": analysis}
        support = self.support()
        self.notes.append(
            f"받침을 고정하고 {span} 구합니다. 시험 주파수 범위 안의 공진을 찾는 진동 응답 "
            "조사에 해당합니다."
        )
        return {
            "constraints": [{"name": "받침 고정", "type": "fixed_support", "on": support}],
            "loads": [],
            "analysis": analysis,
        }
