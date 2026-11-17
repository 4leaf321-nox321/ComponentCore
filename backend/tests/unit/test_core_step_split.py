"""STEP 을 **바디마다 이력 하나로** 가져온다(2026-11-17, 사용자 요청).

올린 STEP 이 바디 여럿이면 바디마다 `import_step` 노드(`body`)에 끝을 `group`
(`names: "body"`)으로 묶는다 — 피처 트리에 바디가 하나씩 선다. 한 노드(`bodies: "leaf"`)로
가져올 때와 **바디 이름 · 부피 · 자리가 같아야** 한다(이미 건 해석 조건 · 받는 쪽의 짝짓기가
그 이름을 쓴다).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from build123d import Box, Compound, Cylinder, Edge, Location, Shape, export_step

from app.core.recipe import RecipeError, evaluate, parse, step_import, topology
from app.core.recipe.schema import RecipeValidationError
from app.modules.works.services import MAX_SPLIT_BODIES, _body_node_id, step_recipe


def _put(shape: Shape, label: str, at: tuple[float, float, float] = (0, 0, 0)) -> Shape:
    one = shape.moved(Location(at))
    one.label = label
    return one


def _step(tmp_path: Path) -> Path:
    """이름에 피처 id 로 못 쓰는 글자(공백 · 괄호 · 숫자 시작)가 있고, 같은 이름이 겹치고,
    선뿐인 부품이 섞인 조립."""
    path = tmp_path / "assy.step"
    shape = Compound(
        children=[
            _put(Box(30, 30, 2), "1번 판"),
            _put(Cylinder(2, 10), "M6 볼트(1)", (10, 0, 6)),
            _put(Cylinder(2, 10), "Bolt", (-10, 0, 6)),
            _put(Cylinder(2, 10), "Bolt", (0, 10, 6)),
            _put(Compound([Edge.make_line((0, 0, 0), (0, 0, 10))]), "축선"),
        ]
    )
    export_step(shape, path)
    return path


def _run(recipe: dict[str, Any], path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    made = evaluate(parse(recipe), resolve_file=lambda key: path.parent / key)
    return topology.bodies(made.shape), made.warnings


def test_바디마다_노드_하나_끝에_묶음_이름_부피_자리가_한_노드와_같다(tmp_path: Path) -> None:
    path = _step(tmp_path)
    names = [one.name for one in step_import.split(path)[0]]
    assert len(names) == 4
    recipe = step_recipe("assy.step", path.name, names)
    nodes = recipe["nodes"]
    assert [one["op"] for one in nodes] == ["import_step"] * 4 + ["group"]
    assert [one["label"] for one in nodes[:4]] == names, (
        "사람이 보는 이름은 STEP 의 이름 그대로"
    )
    assert all(one["body"] == one["label"] for one in nodes[:4])
    ids = [one["id"] for one in nodes[:4]]
    assert len(set(ids)) == 4 and "imported" not in ids
    assert nodes[-1] == {
        "id": "imported",
        "op": "group",
        "label": "assy.step",
        "targets": ids,
        "names": "body",
    }

    split, split_notes = _run(recipe, path)
    whole, whole_notes = _run(step_recipe("assy.step", path.name, names[:1]), path)
    assert [row["name"] for row in split] == [row["name"] for row in whole] == names
    for one, other in zip(split, whole, strict=True):
        assert one["volume"] == pytest.approx(other["volume"])
        assert one["centroid"] == pytest.approx(other["centroid"], abs=1e-6)
    # 파일에 대한 말(선뿐인 부품을 뺐다)은 한 번만 — 바디마다 되풀이하지 않는다.
    assert split_notes == whole_notes
    assert sum("선 · 점뿐인 부품" in one for one in split_notes) == 1


def test_피처_id_는_글자_숫자_밑줄만_겹치지_않게() -> None:
    taken = {"imported"}
    made = [
        _body_node_id(name, taken)
        for name in ["1번 판", "M6 볼트(1)", "Bolt", "Bolt", "  ", "x" * 60]
    ]
    assert made[0] == "b_1번_판"
    assert made[1] == "M6_볼트_1"
    assert made[2:4] == ["Bolt", "Bolt_2"]
    assert made[4] == "body"
    assert len(made[5]) <= 40
    parse(
        {
            "nodes": [
                {"id": one, "op": "box", "length": 1, "width": 1, "height": 1} for one in made
            ]
        }
    )


def test_바디가_하나이거나_너무_많으면_한_노드(tmp_path: Path) -> None:
    single = step_recipe("one.step", "f", ["전체"])
    assert [one["op"] for one in single["nodes"]] == ["import_step"]
    assert "body" not in single["nodes"][0]
    many = step_recipe("many.step", "f", [f"b{n}" for n in range(MAX_SPLIT_BODIES + 1)])
    assert len(many["nodes"]) == 1


def test_없는_바디를_고르면_있는_것을_말한다(tmp_path: Path) -> None:
    path = _step(tmp_path)
    recipe = {
        "nodes": [
            {
                "id": "b",
                "op": "import_step",
                "file": path.name,
                "bodies": "leaf",
                "body": "없는 것",
            }
        ]
    }
    with pytest.raises(RecipeError, match=r"‘없는 것’ 바디가 없습니다.*Bolt"):
        _run(recipe, path)
    with pytest.raises(RecipeValidationError, match="bodies='leaf'"):
        parse({"nodes": [{"id": "b", "op": "import_step", "file": "f", "body": "Bolt"}]})


def test_같은_파일은_한_번만_읽는다(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _step(tmp_path)
    reads: list[Path] = []
    real = step_import.read

    def counted(one: Path) -> Shape:
        reads.append(one)
        return real(one)

    monkeypatch.setattr(step_import, "read", counted)
    step_import._SPLIT_CACHE.clear()
    names = [one.name for one in step_import.split(path)[0]]
    _run(step_recipe("assy.step", path.name, names), path)
    assert len(reads) == 1, "바디 넷을 노드 넷으로 가져와도 STEP 은 한 번 읽는다"
    # 파일이 바뀌면 다시 읽는다.
    export_step(Box(5, 5, 5), path)
    step_import.split(path)
    assert len(reads) == 2
