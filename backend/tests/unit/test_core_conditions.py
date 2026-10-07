"""해석 조건 — 솔버를 모르는 중립 표현. 틀린 자리를 짚고, 식을 설계점마다 푼다."""

from __future__ import annotations

from typing import Any

import pytest

from app.core import conditions
from app.core.conditions import ConditionError, parse, resolve, spec

FULL: dict[str, Any] = {
    "named_selections": [
        {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}},
        {
            "name": "볼트구멍",
            "entity": "face",
            "select": {"what": "faces", "kind": "cylinder", "radius": 4.25},
        },
    ],
    "materials": [
        {
            "apply_to": "전체",
            "ref": {"source": "matnexus", "code": "M-000123", "name": "SPCC"},
            "payload": {"density": 7850.0, "density_unit": "kg/m3"},
        }
    ],
    "constraints": [{"name": "고정", "type": "fixed_support", "on": "바닥"}],
    "loads": [
        {
            "name": "볼트",
            "type": "bolt_pretension",
            "on": "볼트구멍",
            "preload": "=토크계수 * 8000",
            "unit": "N",
        },
        {"name": "중력", "type": "standard_earth_gravity", "direction": [0, 0, -1]},
    ],
    "analysis": {"type": "modal", "prestressed": True, "modes": 6},
}


def test_한_벌을_읽고_되돌려_준다() -> None:
    got = parse(FULL)
    assert [one.name for one in got.named_selections] == ["바닥", "볼트구멍"]
    assert got.analysis.type == "modal" and got.analysis.modes == 6
    # 물성은 **해석하지 않는다** — 받은 것을 그대로 들고 있는다.
    assert got.materials[0].payload["density_unit"] == "kg/m3"
    # 단위계는 **이름 하나**다 — 낱낱이 적게 두면 닫히지 않는 계(`mm·kg·s·N`)를 적을 수
    # 있고, 그런 것은 아무도 안 볼 때까지 조용하다가 어느 날 10⁶ 배 틀린다.
    assert got.units.system == "mm_n_tonne"


def test_없는_이름표를_가리키면_지금_말한다() -> None:
    """내보낸 뒤 해석 쪽에서 0 개를 집으면 **하중 없는 해석**이 끝까지 돈다."""
    with pytest.raises(ConditionError, match="선택 그룹 ‘옆면’이"):
        parse(
            {**FULL, "constraints": [{"name": "고정", "type": "fixed_support", "on": "옆면"}]}
        )
    # 있는 이름을 함께 알려 준다 — 오타를 그 자리에서 고치게.
    try:
        parse(
            {**FULL, "constraints": [{"name": "고정", "type": "fixed_support", "on": "옆면"}]}
        )
    except ConditionError as failure:
        assert "바닥" in str(failure) and "볼트구멍" in str(failure)


def test_이름표가_겹치면_막는다() -> None:
    doubled = [FULL["named_selections"][0], FULL["named_selections"][0]]
    with pytest.raises(ConditionError, match="중복됩니다"):
        parse({**FULL, "named_selections": doubled, "constraints": [], "loads": []})


def test_모르는_종류는_자리를_짚어_말한다() -> None:
    with pytest.raises(ConditionError, match=r"loads\.0\.type"):
        parse({**FULL, "loads": [{"name": "x", "type": "춤추기", "on": "바닥"}]})


def test_식은_설계점마다_풀린다() -> None:
    """**받는 쪽은 식을 풀 수 없다.** 점마다 풀린 값을 내보내야 한다."""
    got = resolve(FULL, {"토크계수": 0.9})
    assert got["loads"][0]["preload"] == 7200.0
    # 안 푼 원본은 그대로다 — 스터디의 conditions.json 은 식을 들고 있다.
    assert FULL["loads"][0]["preload"] == "=토크계수 * 8000"

    다른점 = resolve(FULL, {"토크계수": 0.5})
    assert 다른점["loads"][0]["preload"] == 4000.0


def test_모르는_변수를_쓰면_말해_준다() -> None:
    with pytest.raises(ConditionError, match="식을 풀지 못했습니다"):
        resolve(FULL, {"다른이름": 1})


def test_사양표가_화면과_AI_가_쓸_만큼_말해_준다() -> None:
    """종류를 더할 때 화면을 고치지 않으려면, 칸 목록이 서버에서 와야 한다."""
    got = spec()
    assert set(got["groups"]) == {
        "constraints",
        "loads",
        "contacts",
        "initial",
        "mesh_hints",
    }
    assert "bolt_pretension" in got["groups"]["loads"]["types"]
    assert "fixed_support" in got["groups"]["constraints"]["types"]
    assert "on" in got["groups"]["loads"]["fields"]
    assert got["entities"] == ["face", "edge", "vertex", "body"]


def test_물성은_원본_옆에_변환값을_나란히_싣는다() -> None:
    """**MatNexus 가 한 계로 주지 않는다**(2026-09-24 실측): 밀도만 `tonne/mm3` 이고 나머지
    `value_si` 는 진짜 SI 다. 우리 STEP 은 mm 이라 해석은 mm·tonne·s 로 푸는데, 그대로
    넘기면 밀도는 맞고 **탄성계수가 10⁶ 배 틀린다** — 결과가 안 나오는 게 아니라 그럴듯한
    값이 나오고 틀린다.

    그래서 값을 그 계로 옮겨 **원본 옆에** 놓는다. 원본은 안 건드린다 — 감사할 때는 원본,
    풀 때는 변환값이다.
    """
    raw = {
        "units": {"system": "mm_n_tonne"},
        "materials": [
            {
                "payload": {
                    "density": 2.68e-09,
                    "density_unit": "tonne/mm3",
                    "declared_properties": [
                        {
                            "item": "탄성계수",
                            "si_unit": "Pa",
                            "points": [{"temperature_C": 22, "value_si": 7.0e10}],
                        },
                        {
                            "item": "비열",
                            "si_unit": "J/(kg.K)",
                            "points": [{"temperature_C": 22, "value_si": 880.0}],
                        },
                    ],
                }
            }
        ],
    }
    got = conditions.resolve(raw, {})

    # 선언이 **닫힌 계 전부**를 편다 — 받는 쪽이 제멋대로 가정하지 않게.
    assert got["units"]["system"] == "mm_n_tonne"
    assert got["units"]["stress"] == "MPa" and got["units"]["mass"] == "tonne"

    made = got["materials"][0]["converted"]
    assert made["density"] == pytest.approx(2.68e-09)
    한 = {one["item"]: one for one in made["properties"]}
    assert 한["탄성계수"]["unit"] == "MPa"
    assert 한["탄성계수"]["points"][0]["value"] == pytest.approx(70000.0)
    # 비열은 길이가 제곱으로 들어가 10⁶ 배 — 「응력이니까 10⁶」 같은 눈대중으로는 안 나온다.
    assert 한["비열"]["points"][0]["value"] == pytest.approx(8.8e8)

    # **원본은 그대로다.** 이것이 감사의 정본이다.
    payload = got["materials"][0]["payload"]
    assert payload["density"] == 2.68e-09
    assert payload["declared_properties"][0]["points"][0]["value_si"] == 7.0e10


def test_SI_를_고르면_밀도가_제자리를_찾는다() -> None:
    raw = {
        "units": {"system": "si"},
        "materials": [{"payload": {"density": 7.93e-09, "density_unit": "tonne/mm3"}}],
    }
    got = conditions.resolve(raw, {})
    assert got["units"]["stress"] == "Pa"
    assert got["materials"][0]["converted"]["density"] == pytest.approx(7930.0)
    assert got["materials"][0]["converted"]["density_unit"] == "kg/m3"


def test_밀도는_옛_응답도_새_응답도_같은_값으로_옮긴다() -> None:
    """MatNexus 재료 응답의 **모양이 바뀌었다**(b64cd5c, 2026-09-25): 전에는 `density` 가 화면
    표시값(tonne/mm3)이고 SI 가 곁의 `density_si` 였는데, 이제 `density` 가 SI(kg/m³)이고
    `density_si` 는 없다. 저장된 조건 · DOE 스냅샷에는 옛 모양이 남아 있으므로 둘 다 같은 값이
    나와야 한다 — `density` 의 단위를 가정하면 한쪽이 10¹² 배 틀린다."""
    옛 = {"density": 7.85e-9, "density_unit": "tonne/mm3", "density_si": 7850.0}
    새 = {"density": 7850.0, "density_unit": "kg/m3"}
    for system, 기대 in (("mm_n_tonne", 7.85e-9), ("si", 7850.0)):
        for payload in (옛, 새):
            made = conditions.converted_material(payload, system)
            assert made["density"] == pytest.approx(기대), (system, payload)
            assert "unconverted" not in made or not made["unconverted"]


def test_못_바꾼_것은_못_바꿨다고_적는다() -> None:
    """조용히 원래 값을 남기면 받는 쪽이 그것을 **새 단위인 줄 알고** 그대로 푼다."""
    raw = {
        "materials": [
            {
                "payload": {
                    "density": 1.0,
                    "density_unit": "furlong/fortnight",
                    "declared_properties": [
                        {"item": "이상한것", "si_unit": "그램", "points": [{"value_si": 3.0}]}
                    ],
                }
            }
        ]
    }
    made = conditions.resolve(raw, {})["materials"][0]["converted"]
    assert made["density"] == 1.0, "짐작해서 바꾸지 않는다"
    assert "밀도(furlong/fortnight)" in made["unconverted"]
    assert any("이상한것" in one for one in made["unconverted"])


def test_없는_바디에_물성을_붙이면_막는다() -> None:
    """물성을 없는 바디에 붙이면 해석이 그 바디를 **맨몸으로** 푼다 — 값이 안 나오는 게
    아니라 기본값으로 풀려 그럴듯한 답이 나온다. 이름표를 가리킬 때와 같은 까닭이다."""
    raw = {"materials": [{"apply_to": ["기둥"], "payload": {}}]}
    # 바디를 안 주면 검사하지 않는다 — 도면을 못 만드는 자리에서 저장이 막히면 안 된다.
    assert parse(raw).materials[0].apply_to == ["기둥"]

    parse(raw, ["바닥판", "기둥"])  # 있으면 통과
    with pytest.raises(ConditionError) as failure:
        parse(raw, ["바닥판"])
    assert "바디 ‘기둥’이(가) 없습니다" in str(failure.value)
    assert "존재하는 바디: 바닥판" in str(failure.value), "무엇을 고를 수 있는지 말해 준다"

    # 「전체」 는 언제나 된다 — 모든 바디라는 뜻이다.
    parse({"materials": [{"apply_to": ["전체"], "payload": {}}]}, ["바닥판"])


def test_물성은_바디_여럿에_붙고_옛_문자열도_읽는다() -> None:
    """파트 셋에 같은 재료를 줄 때 **한 번만 담는다.** 예전(문자열 하나)에는 같은 재료를 세 번
    담아야 했고, 덱의 재료 번호도 셋이 되어 받는 쪽이 같은 재료인지 알 수 없었다."""
    raw = {"materials": [{"apply_to": ["바닥판", "기둥", "기둥"], "payload": {}}]}
    assert parse(raw, ["바닥판", "기둥"]).materials[0].apply_to == ["바닥판", "기둥"]

    # 저장된 조건 · DOE 스냅샷에는 옛 모양이 남아 있다 — 읽을 수 있어야 한다.
    assert parse({"materials": [{"apply_to": "기둥", "payload": {}}]}).materials[
        0
    ].apply_to == ["기둥"]
    # 칸을 안 주면 예전처럼 모든 바디다(부르는 쪽이 안 적었을 때의 뜻을 바꾸지 않는다).
    assert parse({"materials": [{"payload": {}}]}).materials[0].apply_to == ["전체"]
    # **빈 목록은 「아직 안 붙었다」** 다 — 담아 두고 파트마다 고르는 동안의 모양.
    assert parse({"materials": [{"apply_to": [], "payload": {}}]}).materials[0].apply_to == []


def test_바디_하나에_물성_둘은_막는다() -> None:
    """둘이면 해석 쪽이 어느 것으로 풀지 모른다 — 사람이 고른 것과 다를 수 있다."""
    둘 = {
        "materials": [
            {"apply_to": ["기둥"], "payload": {}},
            {"apply_to": ["바닥판", "기둥"], "payload": {}},
        ]
    }
    with pytest.raises(ConditionError) as failure:
        parse(둘)
    assert "‘기둥’에 물성이 2개 지정되었습니다" in str(failure.value)
    assert "materials[0]" in str(failure.value), "어느 것과 겹치는지 말한다"

    # 「전체」 는 모든 바디라서, 다른 재료가 한 바디라도 가리키면 겹친다.
    with pytest.raises(ConditionError) as failure:
        parse(
            {
                "materials": [
                    {"apply_to": ["전체"], "payload": {}},
                    {"apply_to": ["기둥"], "payload": {}},
                ]
            }
        )
    assert "‘기둥’에 물성이 2개 지정됩니다" in str(failure.value)

    # 담아만 둔 재료(빈 목록)는 몇 개든 겹치지 않는다.
    parse({"materials": [{"apply_to": [], "payload": {}}, {"apply_to": [], "payload": {}}]})


def test_converted_는_출처가_달라도_한_모양이다() -> None:
    """등록 재료는 밀도 · 푸아송비가 payload 의 **칸**으로 오고 문헌은 `values[]` 안에
    **줄**로 온다. 그대로 두면 받는 쪽이 출처에 따라 두 군데를 봐야 한다."""
    등록 = conditions.converted_material(
        {"density_si": 2680.0, "poisson_ratio": 0.33}, "mm_n_tonne"
    )
    문헌 = conditions.converted_material(
        {
            "values": [
                {"property_key": "physical.density", "value_num": 2680.0, "unit": "kg/m^3"},
                {
                    "property_key": "mechanical.poisson_ratio",
                    "value_num": 0.33,
                    "unit": "1",
                },
            ]
        },
        "mm_n_tonne",
    )
    for made in (등록, 문헌):
        assert made["density"] == pytest.approx(2.68e-09)
        assert made["density_unit"] == "tonne/mm3"
        assert made["poisson_ratio"] == pytest.approx(0.33)


def test_두_창고가_같은_열쇠를_내놓는다() -> None:
    """**등록 재료의 물성 줄에는 기계가 읽을 이름이 없다**(한글 라벨 `item` 뿐). 문헌은
    `property_key` 가 있다 — 그대로 두면 받는 쪽이 출처에 따라 다른 규칙으로 「어느 것이
    영률인가」 를 풀어야 한다.

    MatNexus 물성 사전이 그 다리를 이미 들고 있다(`internal_items`). 우리가 한글 표를 따로
    만들면 그쪽이 항목을 하나 더하는 날 우리만 모른다."""
    사전 = {"탄성계수": "mechanical.youngs_modulus", "비열": "thermal.specific_heat"}
    등록 = conditions.converted_material(
        {
            "density_si": 2680.0,
            "poisson_ratio": 0.33,
            "declared_properties": [
                {"item": "탄성계수", "si_unit": "Pa", "points": [{"value_si": 7.0e10}]}
            ],
        },
        "mm_n_tonne",
        사전,
    )
    문헌 = conditions.converted_material(
        {
            "values": [
                {"property_key": "physical.density", "value_num": 2680.0, "unit": "kg/m^3"},
                {
                    "property_key": "mechanical.poisson_ratio",
                    "value_num": 0.33,
                    "unit": "1",
                },
                {
                    "property_key": "mechanical.youngs_modulus",
                    "value_num": 7.0e10,
                    "unit": "Pa",
                },
            ]
        },
        "mm_n_tonne",
        사전,
    )
    for made in (등록, 문헌):
        assert made["density_key"] == "physical.density"
        assert made["poisson_key"] == "mechanical.poisson_ratio"
        # **열쇠로 찾는다** — 그것이 이 기능의 요점이다(한글 라벨로 찾지 않는다).
        E = next(
            one for one in made["properties"] if one.get("key") == "mechanical.youngs_modulus"
        )
        assert E["points"][0]["value"] == pytest.approx(70000.0)
        # 셋이 다 있으니 해석에 바로 쓸 수 있다.
        assert "missing_structural" not in made

    # 사전이 없으면 열쇠만 없다 — 값은 그대로 나간다(열쇠는 덤이다).
    없이 = conditions.converted_material(
        {
            "declared_properties": [
                {"item": "탄성계수", "si_unit": "Pa", "points": [{"value_si": 7.0e10}]}
            ]
        },
        "mm_n_tonne",
    )
    assert "key" not in 없이["properties"][0]
    assert 없이["properties"][0]["points"][0]["value"] == pytest.approx(70000.0)


def test_해석에_빠진_것을_고를_때_말한다() -> None:
    """탄성계수 · 푸아송비 · 밀도가 없으면 해석이 **기본값(구조용 강)** 으로 푼다 — 값이 안
    나오는 게 아니라 고유진동수가 틀린 뒤에야 드러난다. 문헌 2663건 중 탄성계수를 가진 것은
    1025건뿐이다."""
    모자람 = conditions.converted_material(
        {
            "values": [
                {"property_key": "physical.density", "value_num": 2680.0, "unit": "kg/m^3"}
            ]
        },
        "mm_n_tonne",
    )
    assert 모자람["missing_structural"] == ["탄성계수", "푸아송비"]

    # **모르는 것과 없는 것은 다르다.** 목록 한 줄에는 값이 아예 안 딸려 온다(2663건을
    # 값째로 끌 수 없다) — 그때 「다 빠졌다」 고 하면 거짓말이다.
    아직 = conditions.converted_material({"name": "무언가"}, "mm_n_tonne")
    assert "missing_structural" not in 아직


def test_여럿을_묶은_선택_그룹은_한_종류여야_한다() -> None:
    """면과 엣지를 섞으면 받는 쪽이 지문을 어느 쪽으로 짝지을지 모른다."""
    묶음 = {
        "name": "바닥과 구멍",
        "entity": "face",
        "select": {
            "any": [{"what": "faces", "role": "bottom"}, {"what": "faces", "radius": 4.25}]
        },
    }
    assert parse({"named_selections": [묶음]}).named_selections[0].select == 묶음["select"]

    섞음 = {
        **묶음,
        "select": {"any": [{"what": "faces", "role": "bottom"}, {"what": "edges"}]},
    }
    with pytest.raises(ConditionError, match="한 종류여야 합니다"):
        parse({"named_selections": [섞음]})
    with pytest.raises(ConditionError, match="하나 이상"):
        parse({"named_selections": [{**묶음, "select": {"any": []}}]})


def test_구속의_성분은_화면에_자유_고정_변위량으로_고르라고_알린다() -> None:
    fields = conditions.spec()["groups"]["constraints"]["fields"]
    for axis in ("x", "y", "z"):
        assert fields[axis]["component"] is True
        assert fields[axis]["only_for"] == ["displacement", "remote_displacement"]
        assert fields[f"r{axis}"]["only_for"] == ["remote_displacement"]
        # 칸마다 단위 — 변위량은 단위계의 길이, 회전은 도.
        assert fields[axis]["dimension"] == "length" and fields[f"r{axis}"]["unit"] == "도"


def test_원통_지지는_반지름_축_접선마다_풀_수_있고_기본은_고정이다() -> None:
    raw: dict[str, Any] = {
        "named_selections": [
            {"name": "구멍", "entity": "face", "select": {"what": "faces", "kind": "cylinder"}}
        ],
        "constraints": [
            {"name": "핀", "type": "cylindrical", "on": "구멍", "tangential": "free"}
        ],
    }
    one = parse(raw).constraints[0]
    assert (one.radial, one.axial, one.tangential) == ("fixed", "fixed", "free")
    bad = {**raw, "constraints": [{**raw["constraints"][0], "axial": "0"}]}
    with pytest.raises(ConditionError):
        parse(bad)


def test_종류가_정하는_방향은_사양표에_실려_화면이_잠긴_칸으로_보인다() -> None:
    group = spec()["groups"]["constraints"]
    assert group["fields"]["radial"]["only_for"] == ["cylindrical"]
    assert group["fields"]["cs"]["only_for"] == ["displacement", "remote_displacement"]
    implied = group["implied"]
    # 고를 수 있는 종류(변위 · 원통)는 잠긴 칸이 없고, 나머지는 방향마다 적혀 있다.
    assert set(implied) == {
        "fixed_support",
        "frictionless",
        "compression_only",
        "elastic_support",
    }
    assert [(one["label"], one["hold"]) for one in implied["frictionless"]] == [
        ("법선", "fixed"),
        ("접선", "free"),
    ]


def test_원격_변위는_이동_회전을_방향마다_정하고_원격점은_좌표계_원점일_수_있다() -> None:
    base = {
        "named_selections": [
            {"name": "구멍", "entity": "face", "select": {"what": "faces", "role": "bottom"}}
        ],
        "coordinate_systems": [{"name": "핀 중심", "origin": [0, 0, 5]}],
    }
    one = {"name": "핀", "type": "remote_displacement", "on": "구멍", "x": 0, "y": 0}
    got = parse({**base, "constraints": [{**one, "z": 0, "rz": None, "rx": 0, "ry": 0}]})
    held = got.constraints[0]
    assert (held.rx, held.ry, held.rz) == (0, 0, None)
    assert (held.location, held.behavior) == ("centroid", "deformable")
    # 원격점을 좌표계 원점으로 — 좌표계를 골라야 한다(전역 원점은 모델과 상관없다).
    parse({**base, "constraints": [{**one, "location": "cs_origin", "cs": "핀 중심"}]})
    with pytest.raises(ConditionError, match="좌표계를 선택하십시오"):
        parse({**base, "constraints": [{**one, "location": "cs_origin"}]})


def test_탄성_지지는_기초_강성이_있어야_한다() -> None:
    base = {
        "named_selections": [
            {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}}
        ],
    }
    one = {"name": "패드", "type": "elastic_support", "on": "바닥"}
    with pytest.raises(ConditionError, match="기초 강성이 없습니다"):
        parse({**base, "constraints": [one]})
    assert parse({**base, "constraints": [{**one, "stiffness": "=강성"}]}).constraints[0]


LOAD_BASE: dict[str, Any] = {
    "named_selections": [
        {"name": "윗면", "entity": "face", "select": {"what": "faces", "role": "top"}},
        {"name": "볼트", "entity": "face", "select": {"what": "faces", "kind": "cylinder"}},
    ],
}


def test_하중은_빠진_값과_쓸_수_없는_방향을_저장할_때_말한다() -> None:
    def load(**one: Any) -> dict[str, Any]:
        return {**LOAD_BASE, "loads": [{"name": "하중", "on": "윗면", **one}]}

    cases = [
        (load(type="force", direction=[0, 0, 1]), "크기가 없습니다"),
        (load(type="force", magnitude=1), "방향이 없습니다"),
        (load(type="force", magnitude=1, direction=[0, 0, 0]), "0 벡터"),
        (load(type="force", magnitude=1, direction="normal"), "압력에만"),
        (load(type="moment", magnitude=1, on="", direction=[0, 0, 1]), "선택 그룹이 없습니다"),
        (load(type="bolt_pretension"), "예압"),
    ]
    for raw, message in cases:
        with pytest.raises(ConditionError, match=message):
            parse(raw)
    # 식은 설계점마다 풀리므로 0 벡터인지 여기서 모른다 — 막지 않는다.
    parse(load(type="force", magnitude="=힘", direction=["=a", 0, 0]))


def test_하중의_사양표는_종류마다_칸_단위_설명을_싣는다() -> None:
    group = spec()["groups"]["loads"]
    fields = group["fields"]
    assert fields["direction"]["normal_for"] == ["pressure"]
    assert "standard_earth_gravity" not in fields["on"]["only_for"]
    assert fields["unit"]["hidden"] is True
    assert group["dimensions"]["moment"] == "moment"
    assert fields["type"]["labels"]["pressure"] == "압력"
    assert set(group["notes"]) == set(fields["type"]["enum"])
    units = {one["key"]: one for one in spec()["unit_systems"]}
    assert units["mm_n_tonne"]["moment"] == "N*mm" and units["si"]["moment"] == "N*m"


def test_조건은_mm_N_t_로_적고_내보낼_때만_고른_계로_옮긴다() -> None:
    """화면 · 식 · 도면 치수가 한 계(mm)라 섞이지 않는다. SI 는 **내보내기** 단위계다."""
    raw = {
        **LOAD_BASE,
        "units": {"system": "si"},
        "coordinate_systems": [{"name": "끝", "origin": ["=두께*2", 0, 0]}],
        "constraints": [
            {"name": "밀기", "type": "displacement", "on": "윗면", "x": "=두께*0.1", "y": 0},
            {"name": "패드", "type": "elastic_support", "on": "윗면", "stiffness": 2},
        ],
        "loads": [
            {"name": "누름", "type": "pressure", "on": "윗면", "magnitude": "=압력"},
            {
                "name": "밀기",
                "type": "force",
                "on": "윗면",
                "magnitude": 10,
                "direction": [0, 0, -1],
            },
            {
                "name": "비틀기",
                "type": "moment",
                "on": "윗면",
                "magnitude": 5000,
                "direction": [0, 0, 1],
            },
            {"name": "자중", "type": "standard_earth_gravity"},
            {
                "name": "조임",
                "type": "bolt_pretension",
                "on": "볼트",
                "preload": 0.1,
                "unit": "mm",
            },
        ],
    }
    params = {"두께": 5, "압력": 2}
    si = resolve(raw, params)
    held = si["constraints"]
    # 식은 도면 치수(mm) 그대로 풀고, 풀린 값을 옮긴다: 0.5 mm → 0.0005 m. 0 은 0(고정).
    assert held[0]["x"] == pytest.approx(0.0005) and held[0]["y"] == 0
    assert held[1]["stiffness"] == pytest.approx(2e9)  # MPa/mm → Pa/m
    loads = si["loads"]
    assert loads[0]["magnitude"] == pytest.approx(2e6) and loads[0]["unit"] == "Pa"
    assert loads[1]["magnitude"] == 10 and loads[1]["unit"] == "N"
    assert loads[2]["magnitude"] == pytest.approx(5) and loads[2]["unit"] == "N*m"
    assert loads[4]["preload"] == pytest.approx(0.0001) and loads[4]["unit"] == "m"
    assert loads[0]["direction"] == "normal" and loads[3]["direction"] == [0, 0, -1]
    assert si["units"]["system"] == "si" and si["units"]["length"] == "m"
    # 좌표계 원점은 도면 쪽 — 조건 블록에서는 mm 그대로(점 파일의 좌표계는 따로 옮긴다).
    assert si["coordinate_systems"][0]["origin"][0] == 10

    mm = resolve({**raw, "units": {"system": "mm_n_tonne"}}, params)
    assert mm["constraints"][0]["x"] == pytest.approx(0.5)
    assert mm["loads"][0]["unit"] == "MPa" and mm["loads"][4]["unit"] == "mm"


def test_하중의_단위는_mm_N_t_이름만_받는다() -> None:
    one = {"name": "누름", "type": "pressure", "on": "윗면", "magnitude": 1}
    parse({**LOAD_BASE, "loads": [{**one, "unit": "MPa"}]})
    # 내보내기 계가 SI 여도 입력은 mm · N · t — Pa 로 적으면 막는다(10⁶ 배 틀린다).
    with pytest.raises(ConditionError, match="mm·N·t 단위로 입력합니다"):
        parse({**LOAD_BASE, "units": {"system": "si"}, "loads": [{**one, "unit": "Pa"}]})


def test_풀리지_않는_식은_고치는_중에_알린다() -> None:
    raw = {
        **LOAD_BASE,
        "loads": [{"name": "누름", "type": "pressure", "on": "윗면", "magnitude": "=없는것"}],
        "constraints": [{"name": "밀기", "type": "displacement", "on": "윗면", "x": "=두께"}],
    }
    notes = conditions.expression_notes(raw, {"두께": 5})
    assert [(one["where"], one["level"]) for one in notes] == [("하중 ‘누름’ 크기", "warn")]
    assert "알 수 없는 이름" in notes[0]["text"]


def test_마이그레이션_0022_는_SI_로_적힌_값을_mm_N_t_로_옮긴다() -> None:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[2] / "migrations/versions/0022_conditions_input_mm.py"
    spec_ = importlib.util.spec_from_file_location("m0022", path)
    assert spec_ and spec_.loader
    module = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(module)
    old: dict[str, Any] = {
        "units": {"system": "si"},
        "constraints": [{"name": "밀기", "type": "displacement", "x": 0.0005, "rx": 5}],
        "loads": [
            {"name": "누름", "type": "pressure", "magnitude": "=압력", "unit": "Pa"},
            {"name": "조임", "type": "bolt_pretension", "preload": 0.0001, "unit": "m"},
        ],
    }
    new = module.to_input(old)
    assert new["units"]["system"] == "si"  # 내보내기 계는 그대로 — 내보내는 값이 같다
    assert new["constraints"][0]["x"] == 0.5 and new["constraints"][0]["rx"] == 5
    assert new["loads"][0] == {
        **old["loads"][0],
        "magnitude": "=(압력)*0.000001",
        "unit": "MPa",
    }
    assert new["loads"][1]["preload"] == 0.1 and new["loads"][1]["unit"] == "mm"
    # 옮긴 값을 SI 로 내보내면 옛 값과 같다.
    raw = {
        "named_selections": [
            {"name": "a", "entity": "face", "select": {"what": "faces", "role": "top"}}
        ],
        "units": {"system": "si"},
        "constraints": [{**new["constraints"][0], "on": "a"}],
    }
    assert resolve(raw, {})["constraints"][0]["x"] == pytest.approx(0.0005)
    # 되돌리면 정확히 제자리 — 내렸다 다시 올려도 두 번 옮겨지지 않는다.
    assert module.to_si(new) == old


TWO_FACES: dict[str, Any] = {
    "named_selections": [
        {"name": "윗판", "entity": "face", "select": {"what": "faces", "role": "top"}},
        {"name": "아랫판", "entity": "face", "select": {"what": "faces", "role": "bottom"}},
        {"name": "몸", "entity": "body", "select": {"what": "bodies"}},
    ],
}


def test_접촉은_종류에_필요한_값을_저장할_때_말한다() -> None:
    one = {"name": "맞닿음", "type": "frictional", "source": "윗판", "target": "아랫판"}
    with pytest.raises(ConditionError, match="마찰계수가 없습니다"):
        parse({**TWO_FACES, "contacts": [one]})
    got = parse({**TWO_FACES, "contacts": [{**one, "friction": 0.2}]}).contacts[0]
    # 고르는 칸은 기본값 — 예전에 비워 둔 "" 도 기본값으로 읽는다.
    assert (got.formulation, got.behavior, got.interface_treatment) == (
        "program_controlled",
        "program_controlled",
        "add_offset_ramped",
    )
    legacy = {**one, "friction": 0.2, "formulation": "", "behavior": ""}
    assert parse({**TWO_FACES, "contacts": [legacy]}).contacts[0].formulation == (
        "program_controlled"
    )
    with pytest.raises(ConditionError, match="MPC"):
        parse({**TWO_FACES, "contacts": [{**one, "friction": 0.2, "formulation": "mpc"}]})
    with pytest.raises(ConditionError, match="같습니다"):
        parse({**TWO_FACES, "contacts": [{**one, "type": "bonded", "target": "윗판"}]})


def test_초기조건은_종류마다_필요한_값이_있고_내보낼_때_단위를_채운다() -> None:
    cases = [
        ({"type": "environment_temperature"}, "온도가 없습니다"),
        ({"type": "temperature", "value": 80}, "바디 선택 그룹이 없습니다"),
        ({"type": "velocity", "on": "몸"}, "속도"),
    ]
    for one, message in cases:
        with pytest.raises(ConditionError, match=message):
            parse({**TWO_FACES, "initial": [one]})
    raw = {
        **TWO_FACES,
        "units": {"system": "si"},
        "initial": [
            {"type": "environment_temperature", "value": 22},
            {"type": "velocity", "on": "몸", "vector": [0, 0, -5000]},
        ],
    }
    initial = resolve(raw, {})["initial"]
    assert initial[0]["value"] == 22 and initial[0]["unit"] == "C"
    # 속도는 mm/s 로 적고 SI 로 내보낸다.
    assert initial[1]["vector"] == [0, 0, -5] and initial[1]["unit"] == "m/s"


def test_메시_힌트는_고르는_칸이_정해져_있고_비운_것은_받는_쪽이_정한다() -> None:
    hint = parse({"mesh_hints": [{"on": "전체", "element_size": 2, "method": ""}]}).mesh_hints[
        0
    ]
    assert (hint.method, hint.order) == ("automatic", "program_controlled")
    with pytest.raises(ConditionError):
        parse({"mesh_hints": [{"on": "전체", "method": "hexa"}]})
    group = spec()["groups"]["mesh_hints"]
    assert group["fields"]["on"]["whole"] == "전체"
    assert group["fields"]["element_size"]["unit"] == "mm"
    assert "권장 사항" in group["intro"]
    assert spec()["groups"]["contacts"]["fields"]["type"]["labels"]["bonded"] == "본딩(접합)"


def test_해석_설정은_종류마다_꼭_필요한_값을_저장할_때_말한다() -> None:
    cases = [
        ({"type": "modal", "modes": 0}, "모드 수는 1 이상"),
        ({"type": "harmonic"}, "주파수 범위가 없습니다"),
        ({"type": "harmonic", "frequency_range": [0, 500], "modes": 0}, "모드 중첩"),
        ({"type": "harmonic", "frequency_range": [500, 100]}, "최소 < 최대"),
        ({"type": "explicit"}, "종료 시간이 없습니다"),
        ({"type": "thermal", "thermal_mode": "transient"}, "과도 열 해석에 종료 시간"),
        ({"type": "static", "steps": 0}, "1 이상"),
    ]
    for analysis, message in cases:
        with pytest.raises(ConditionError, match=message):
            parse({"analysis": analysis})
    # 필요한 것이 있으면 된다 — 완전법 조화 응답은 모드 수가 없어도 된다.
    parse({"analysis": {"type": "harmonic", "frequency_range": [0, 500], "method": "full"}})
    parse({"analysis": {"type": "thermal"}})  # 정상 상태는 시간이 필요 없다
    parse({"analysis": {"type": "explicit", "end_time": "=충돌시간"}})
    # 비운 칸은 기본값 — 화면이 「기본 6」 이라고 보여 준 그대로.
    assert parse({"analysis": {"type": "modal", "modes": None}}).analysis.modes == 6


def test_내보낼_때는_그_종류의_칸만_기본값을_채워_싣는다() -> None:
    def exported(analysis: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = resolve({"analysis": analysis}, {"충돌시간": 0.005})["analysis"]
        return out

    assert exported({"type": "modal", "modes": 10}) == {
        "type": "modal",
        "modes": 10,
        "frequency_range": None,
        "prestressed": False,
        "solver": "program_controlled",
    }
    explicit = exported({"type": "explicit", "end_time": "=충돌시간", "modes": 12})
    assert explicit == {
        "type": "explicit",
        "end_time": 0.005,
        "output_count": 20,
        "mass_scaling_dt": None,
    }
    harmonic = exported(
        {"type": "harmonic", "frequency_range": [10, 500], "damping_ratio": 0.02}
    )
    assert harmonic["solution_intervals"] == 10 and harmonic["method"] == "mode_superposition"
    assert harmonic["modes"] == 6 and "large_deflection" not in harmonic
    static = exported({"type": "static", "large_deflection": True})
    assert set(static) == {"type", "large_deflection", "steps", "substeps", "solver"}
    steady = exported({"type": "thermal"})
    assert set(steady) == {"type", "solver", "thermal_mode"}
    transient = exported({"type": "thermal", "thermal_mode": "transient", "end_time": 60})
    assert transient["end_time"] == 60 and transient["output_count"] == 20


def test_해석_설정의_사양표는_종류마다_설명과_칸을_싣는다() -> None:
    analysis = spec()["analysis"]
    assert set(analysis["notes"]) == set(analysis["properties"]["type"]["enum"])
    assert analysis["properties"]["type"]["labels"]["explicit"] == "명시적 동해석(충돌·낙하)"
    assert analysis["properties"]["end_time"]["only_for"] == ["explicit", "thermal"]
    assert analysis["properties"]["frequency_range"]["range"] is True
    assert analysis["intro"]


SPOTS: dict[str, Any] = {
    "named_selections": [
        {"name": "윗면", "entity": "face", "select": {"what": "faces", "role": "top"}},
        {"name": "구멍", "entity": "face", "select": {"what": "faces", "kind": "cylinder"}},
        {
            "name": "가까운 면",
            "entity": "face",
            "select": {"what": "faces", "near": [5, 0, 0], "limit": 1},
        },
        {"name": "모서리", "entity": "edge", "select": {"what": "edges", "near": [0, 0, 0]}},
        {
            "name": "꼭짓점",
            "entity": "vertex",
            "select": {"what": "vertices", "near": [0, 0, 0]},
        },
        {"name": "몸", "entity": "body", "select": {"body": "전체"}},
    ],
}


def test_조건마다_받는_선택_그룹의_종류와_모양이_정해져_있다() -> None:
    def load(kind: str, on: str, **more: Any) -> dict[str, Any]:
        one = {"name": "하중", "type": kind, "on": on, "magnitude": 1, "direction": [0, 0, 1]}
        return {**SPOTS, "loads": [{**one, **more}]}

    # 힘은 면 · 엣지 · 점 어디든.
    for on in ("윗면", "모서리", "꼭짓점"):
        parse(load("force", on))
    with pytest.raises(ConditionError, match="면, 엣지, 점 선택 그룹만"):
        parse(load("force", "몸"))
    # 압력은 면만 — 무엇이 잘못인지 말한다.
    with pytest.raises(ConditionError, match="‘모서리’의 종류는 엣지입니다"):
        parse(load("pressure", "모서리"))
    # 베어링은 원통면 — 규칙에 kind: cylinder 가 있어야 한다(가까운 면만으로는 안 된다).
    parse(load("bearing", "구멍"))
    with pytest.raises(ConditionError, match="kind: cylinder 조건이 없어"):
        parse(load("bearing", "가까운 면"))
    # 볼트는 원통면 또는 바디.
    parse(load("bolt_pretension", "몸", preload=1000, magnitude=None, direction=None))

    contact = {"name": "맞닿음", "type": "bonded", "source": "윗면", "target": "모서리"}
    with pytest.raises(ConditionError, match="대상면에는 면 선택 그룹만"):
        parse({**SPOTS, "contacts": [contact]})
    cylinder = {"name": "핀", "type": "cylindrical", "on": "윗면"}
    with pytest.raises(ConditionError, match="원통면만 지정"):
        parse({**SPOTS, "constraints": [cylinder]})
    # 사양표에 실린다 — 화면 · AI 가 같은 것을 본다.
    groups = spec()["groups"]
    assert groups["loads"]["accepts"]["bearing"] == [{"entity": "face", "kind": "cylinder"}]
    assert groups["contacts"]["accepts"]["frictional"] == [{"entity": "face"}]


def test_모멘트_원격_변위는_면_엣지_메시_힌트는_면_엣지_바디() -> None:
    """SimEngBay 가 Mechanical 스코핑 규칙으로 맞춘 표(2026-09-28)."""
    moment = {"name": "비틀기", "type": "moment", "magnitude": 1, "direction": [0, 0, 1]}
    parse({**SPOTS, "loads": [{**moment, "on": "모서리"}]})
    with pytest.raises(ConditionError, match="면, 엣지 선택 그룹만"):
        parse({**SPOTS, "loads": [{**moment, "on": "꼭짓점"}]})
    remote = {"name": "원격", "type": "remote_displacement", "x": 0}
    with pytest.raises(ConditionError, match="면, 엣지 선택 그룹만"):
        parse({**SPOTS, "constraints": [{**remote, "on": "꼭짓점"}]})
    # 바디 그룹(「몸」)에 건 국부 메시는 옛 조건이라 읽기만 한다 — 새로는 파트별 설정으로.
    parse({**SPOTS, "mesh_hints": [{"on": "몸", "element_size": 3}, {"on": "전체"}]})
    with pytest.raises(ConditionError, match="면, 엣지 선택 그룹만"):
        parse({**SPOTS, "mesh_hints": [{"on": "꼭짓점", "element_size": 1}]})
    assert {"entity": "body"} not in spec()["groups"]["mesh_hints"]["accepts"]["*"]


def test_재료를_바꿔_끼우면_그_바디만_옮기고_원본은_그대로다() -> None:
    raw: dict[str, Any] = {
        "materials": [
            {"apply_to": ["받침판"], "ref": {"name": "SECC", "code": "M-1"}, "payload": {}},
            {"apply_to": ["블록"], "ref": {"name": "AL5052", "code": "M-2"}, "payload": {}},
            {"apply_to": [], "ref": {"name": "SUS304", "code": "M-3"}, "payload": {}},
        ]
    }
    swapped = conditions.with_material(raw, ["블록"], "SUS304")
    assert [one["apply_to"] for one in swapped["materials"]] == [["받침판"], [], ["블록"]]
    # 번호로도 고른다. 원본은 안 바뀐다.
    by_code = conditions.with_material(raw, ["블록"], "M-1")
    assert [one["apply_to"] for one in by_code["materials"]] == [["받침판", "블록"], [], []]
    assert raw["materials"][1]["apply_to"] == ["블록"]
    with pytest.raises(ConditionError, match="조건에 없습니다"):
        conditions.with_material(raw, ["블록"], "없는재료")
    twin = {"materials": [*raw["materials"], {"apply_to": [], "ref": {"name": "SECC"}}]}
    with pytest.raises(ConditionError, match="번호"):
        conditions.with_material(twin, ["블록"], "SECC")
    whole = {"materials": [{"apply_to": ["전체"], "ref": {"name": "A"}}, raw["materials"][2]]}
    with pytest.raises(ConditionError, match="‘전체’에 지정되어"):
        conditions.with_material(whole, ["블록"], "SUS304")


def test_고르기는_칸_하나를_바꾸고_배율은_옮긴_값에만_곱한다() -> None:
    raw: dict[str, Any] = {
        "contacts": [{"name": "블록-판", "type": "bonded", "source": "a", "target": "b"}],
        "initial": [{"type": "environment_temperature", "value": 22}],
        "analysis": {"type": "modal"},
    }
    got = conditions.with_choice(
        raw, {"group": "contacts", "item": "블록-판", "field": "type"}, "rough"
    )
    assert got["contacts"][0]["type"] == "rough" and raw["contacts"][0]["type"] == "bonded"
    got = conditions.with_choice(raw, ("initial", 1, "value"), 30)
    assert got["initial"][0]["value"] == 30
    got = conditions.with_choice(raw, {"group": "analysis", "field": "type"}, "static")
    assert got["analysis"]["type"] == "static"
    with pytest.raises(ConditionError, match="없습니다"):
        conditions.with_choice(raw, ("contacts", "없는것", "type"), "rough")

    resolved: dict[str, Any] = {
        "materials": [
            {
                "apply_to": ["판", "블록"],
                "payload": {"x": 1},
                "converted": {
                    "density": 7.85e-9,
                    "properties": [{"item": "탄성계수", "points": [{"value": 200000.0}]}],
                },
            }
        ]
    }
    assert conditions.has_property(resolved["materials"][0]["converted"], "탄성계수")
    assert conditions.has_property(resolved["materials"][0]["converted"], "밀도")
    assert not conditions.has_property(resolved["materials"][0]["converted"], "항복강도")
    scaled = conditions.with_scale(resolved, ["블록"], "탄성계수", 1.1)
    # 판에도 붙은 재료라 블록만 떼어 곱한 한 벌을 더한다 — 판은 원래 값.
    first, extra = scaled["materials"]
    assert first["apply_to"] == ["판"] and "scaled" not in first["converted"]
    assert extra["apply_to"] == ["블록"] and extra["payload"] == {"x": 1}
    assert extra["converted"]["properties"][0]["points"][0]["value"] == pytest.approx(220000)
    assert extra["converted"]["scaled"] == {"탄성계수": 1.1}


def test_정수_칸도_식을_쓰고_풀리면_정수여야_한다() -> None:
    parsed = parse({"analysis": {"type": "modal", "modes": "=모드수"}})
    assert parsed.analysis.modes == "=모드수"
    assert (
        resolve({"analysis": {"type": "modal", "modes": "=모드수"}}, {"모드수": 12})[
            "analysis"
        ]["modes"]
        == 12
    )
    with pytest.raises(ConditionError, match="정수가 아닙니다"):
        resolve({"analysis": {"type": "modal", "modes": "=모드수/2"}}, {"모드수": 7})
    assert (
        parse({"mesh_hints": [{"on": "전체", "inflation_layers": "3"}]})
        .mesh_hints[0]
        .inflation_layers
        == 3
    )


def test_배율은_없는_물성이나_전체에_붙은_재료에는_걸지_않는다() -> None:
    """값은 그대로인데 `scaled` 만 붙으면 받는 쪽은 배율이 걸린 줄 안다."""
    lacks = {"materials": [{"apply_to": ["블록"], "converted": {"density": 1.0}}]}
    with pytest.raises(ConditionError, match="‘탄성계수’ 물성이 없어"):
        conditions.with_scale(lacks, ["블록"], "탄성계수", 1.1)
    whole = {"materials": [{"apply_to": ["전체"], "converted": {"density": 1.0}}]}
    with pytest.raises(ConditionError, match="‘전체’에 지정되어 있어"):
        conditions.with_scale(whole, ["블록"], "밀도", 2.0)
    # 단품(「전체」)에 「전체」 로 걸면 된다.
    single = conditions.with_scale(whole, ["전체"], "밀도", 2.0)
    assert single["materials"][0]["converted"]["density"] == 2.0


# ── 파트별 설정 ───────────────────────────────────────────────────────────────

PARTS = ["지그판", "부품"]


def test_파트별_설정은_있는_파트에_한_번씩_뜻이_맞게() -> None:
    ok = parse(
        {
            "body_settings": [
                {"name": "지그판", "behavior": "rigid", "mesh": {"element_size": 4}},
                {"name": "부품", "representation": "shell"},
            ]
        },
        PARTS,
    )
    assert [one.behavior for one in ok.body_settings] == ["rigid", "deformable"]
    assert ok.body_settings[1].mesh.method == "automatic"

    def refused(settings: list[dict[str, Any]], words: str) -> None:
        with pytest.raises(ConditionError, match=words):
            parse({"body_settings": settings}, PARTS)

    refused([{"name": "없는 파트"}], "파트 ‘없는 파트’이\\(가\\) 없습니다")
    refused([{"name": "부품"}, {"name": "부품", "suppressed": True}], "설정이 2개")
    refused(
        [{"name": "지그판", "behavior": "rigid", "representation": "shell"}],
        "쉘로 표현할 수 없",
    )
    refused(
        [{"name": "지그판", "suppressed": True}, {"name": "부품", "suppressed": True}],
        "모든 파트",
    )
    refused([{"name": "전체"}, {"name": "부품"}], "단일 파트일 때만")


def test_해석에서_뺀_파트에는_조건을_걸_수_없다() -> None:
    raw: dict[str, Any] = {
        "named_selections": [
            # 파트로 거른 면 그룹 — 어느 파트의 것인지 안다.
            {
                "name": "판 아랫면",
                "entity": "face",
                "select": {"what": "faces", "role": "bottom", "body": "지그판"},
            },
            {
                "name": "부품 윗면",
                "entity": "face",
                "select": {"what": "faces", "role": "top", "body": "부품"},
            },
        ],
        "constraints": [{"name": "고정", "type": "fixed_support", "on": "판 아랫면"}],
        "loads": [
            {
                "name": "누름",
                "type": "pressure",
                "on": "부품 윗면",
                "magnitude": 1,
                "unit": "MPa",
            }
        ],
        "body_settings": [{"name": "지그판", "suppressed": True}],
    }
    with pytest.raises(
        ConditionError,
        match="constraints\\[0\\]: 선택 그룹 ‘판 아랫면’은\\(는\\) 해석에서 제외한",
    ):
        parse(raw, PARTS)
    # 제외를 풀면 된다 — 하중은 처음부터 남은 파트에 걸려 있었다.
    raw["body_settings"] = [{"name": "지그판", "behavior": "rigid"}]
    parse(raw, PARTS)


def test_파트_요소_크기도_식이_풀리고_내보내기_단위로_간다() -> None:
    raw = {
        "units": {"system": "si"},
        "body_settings": [{"name": "부품", "mesh": {"element_size": "=두께 / 2"}}],
    }
    out = resolve(raw, {"두께": 6})
    assert out["body_settings"][0]["mesh"]["element_size"] == pytest.approx(0.003)  # 3 mm → m
    assert conditions.has_shell(
        {"body_settings": [{"name": "부품", "representation": "shell"}]}
    )
    assert not conditions.has_shell(raw) and not conditions.has_shell(None)
    # 화면이 표의 열 이름 · 선택지를 사양표에서 읽는다.
    table = spec()["body_settings"]
    assert table["fields"]["behavior"]["labels"] == {"deformable": "변형체", "rigid": "강체"}
    assert table["mesh_fields"]["element_size"]["unit"] == "mm"


def test_국부_메시는_면_엣지와_전체만_받고_옛_바디_대상도_읽는다() -> None:
    groups = spec()["groups"]["mesh_hints"]
    assert groups["label"] == "국부 메시"
    assert [one["entity"] for one in groups["accepts"]["*"]] == ["face", "edge"]
    # 요소 형상 · 차수는 「전체」 에만 — 화면이 면 · 엣지 대상일 때 감춘다.
    assert groups["fields"]["method"]["whole_only"] and groups["fields"]["order"]["whole_only"]
    # 2026-10-04 전에 바디 그룹에 건 힌트 — 저장된 조건 · DOE 스냅샷이 다시 읽혀야 한다.
    legacy = parse(
        {
            "named_selections": [
                {"name": "판 몸통", "entity": "body", "select": {"body": "지그판"}}
            ],
            "mesh_hints": [{"on": "판 몸통", "element_size": 4}],
        },
        PARTS,
    )
    assert legacy.mesh_hints[0].on == "판 몸통"
    with pytest.raises(ConditionError, match="면, 엣지 선택 그룹만"):
        parse(
            {
                "named_selections": [
                    {"name": "꼭짓점", "entity": "vertex", "select": {"what": "vertices"}}
                ],
                "mesh_hints": [{"on": "꼭짓점", "element_size": 1}],
            }
        )


def test_강체_파트에는_고정_지지와_원격_변위만_강체끼리는_접촉하지_않는다() -> None:
    """받는 쪽(Ansys · CalculiX)은 강체에 하중 · 다른 구속 · 강체끼리의 접촉이 오면 멈춘다
    (SimEngBay, 2026-10-04) — 저장에서 미리 말한다."""
    raw: dict[str, Any] = {
        "named_selections": [
            {"name": "판 바닥", "entity": "face",
             "select": {"what": "faces", "body": "지그판", "normal": [0, 0, -1]}},
            {"name": "판 윗면", "entity": "face",
             "select": {"what": "faces", "body": "지그판", "normal": [0, 0, 1]}},
            {"name": "부품 바닥", "entity": "face",
             "select": {"what": "faces", "body": "부품", "normal": [0, 0, -1]}},
        ],
        "constraints": [
            {"name": "고정", "type": "remote_displacement", "on": "판 바닥",
             "x": 0, "y": 0, "z": 0}
        ],
        "contacts": [
            {"name": "닿음", "type": "bonded", "source": "부품 바닥", "target": "판 윗면"}
        ],
        "body_settings": [{"name": "지그판", "behavior": "rigid"}],
    }  # fmt: skip
    parse(raw, PARTS)  # 원격 변위 · 변형체와의 접촉은 된다
    for extra, words in (
        ({"constraints": [{"name": "변위", "type": "displacement", "on": "판 바닥", "x": 0}]},
         "고정 지지와 원격 변위만"),
        ({"loads": [{"name": "누름", "type": "pressure", "on": "판 윗면", "magnitude": 1}]},
         "하중을 지정할 수 없습니다"),
        ({"body_settings": [{"name": "지그판", "behavior": "rigid"},
                            {"name": "부품", "behavior": "rigid"}]},
         "강체 파트끼리의 접촉"),
    ):  # fmt: skip
        with pytest.raises(ConditionError, match=words):
            parse({**raw, **extra}, PARTS)
    # 모양이 틀린 파트별 설정은 쉘 파트가 없는 것으로(500 이 아니라 검증이 말한다).
    assert conditions.shell_parts({"body_settings": 5}) == []


def test_규칙에_what_이_없으면_선언한_종류로_푼다() -> None:
    """질의의 기본은 엣지다 — 면 그룹 `{"role": "bottom"}` 이 엣지 지문으로 나갔다(SimEngBay
    보고, 2026-10-05). 풀 때 그룹의 종류로 채운다."""
    query = conditions.selection_query
    assert query("face", {"role": "bottom"}) == {"role": "bottom", "what": "faces"}
    assert query("vertex", {"near": [0, 0, 0]})["what"] == "vertices"
    many = query("face", {"any": [{"role": "top"}, {"what": "faces", "role": "bottom"}]})
    assert [one["what"] for one in many["any"]] == ["faces", "faces"]
    assert query("edge", {"what": "edges", "kind": "circle"}) == {
        "what": "edges",
        "kind": "circle",
    }
    assert query("face", {}) == {}  # 아직 안 고른 것을 「전부」 로 바꾸지 않는다
    assert query("body", {"body": "판"}) == {"body": "판"}


def test_선언한_종류와_규칙이_어긋나면_막는다() -> None:
    raw = {
        "named_selections": [{"name": "바닥", "entity": "face", "select": {"what": "edges"}}]
    }
    with pytest.raises(ConditionError, match="바닥"):
        parse(raw)
    parse(
        {
            "named_selections": [
                {"name": "바닥", "entity": "face", "select": {"role": "bottom"}}
            ]
        }
    )
