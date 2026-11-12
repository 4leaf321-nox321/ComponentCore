"""STEP 가져오기 — **어떤 꼴로 오든 바디로 가른다**(`import_step` 의 `bodies: "leaf"`).

옛 규칙(`top`, 맨 위 한 층)이 실측(2026-11-12)에서 틀린 꼴마다 하나씩: 멀티바디, 하위 조립(옮긴
자리까지), 이름 없음, 이름 겹침, 솔리드 + 서피스, 닫힌 셸, 선뿐인 부품, CP949 이름. 옛 레시피는
옛 규칙 그대로인지도 본다 — 바디 이름이 바뀌면 이미 건 해석 조건이 끊긴다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from build123d import Box, Compound, Cylinder, Edge, Face, Location, Shape, Shell, export_step

from app.core.recipe import evaluate, parse, topology


def _put(shape: Shape, label: str, at: tuple[float, float, float] = (0, 0, 0)) -> Shape:
    one = shape.moved(Location(at))
    one.label = label
    return one


def _group(
    children: list[Shape], label: str, at: tuple[float, float, float] = (0, 0, 0)
) -> Shape:
    made = Compound(children=children)
    if at != (0, 0, 0):
        made = made.moved(Location(at))
    made.label = label
    return made


def _bodies(path: Path, mode: str | None = "leaf") -> tuple[list[dict[str, Any]], list[str]]:
    node: dict[str, Any] = {"id": "imported", "op": "import_step", "file": path.name}
    if mode is not None:
        node["bodies"] = mode
    made = evaluate(parse({"nodes": [node]}), resolve_file=lambda key: path.parent / key)
    return topology.bodies(made.shape), made.warnings


def _write(shape: Shape, path: Path) -> Path:
    export_step(shape, path)
    return path


def _names(rows: list[dict[str, Any]]) -> list[str]:
    return [row["name"] for row in rows]


def test_멀티바디_파트는_솔리드마다_바디다(tmp_path: Path) -> None:
    path = _write(
        Compound([Box(10, 10, 10), Box(5, 5, 5).moved(Location((20, 0, 0)))]),
        tmp_path / "m.step",
    )
    rows, _ = _bodies(path)
    assert [row["volume"] for row in rows] == [1000.0, 125.0]
    assert len(set(_names(rows))) == 2
    # 옛 규칙은 「전체」 하나로 뭉쳤다 — 옛 레시피(칸 없음)는 그대로다.
    old, _ = _bodies(path, mode=None)
    assert _names(old) == ["전체"] and old[0]["volume"] == 1125.0


def test_하위_조립을_풀고_옮긴_자리를_지킨다(tmp_path: Path) -> None:
    sub = _group(
        [_put(Box(2, 2, 2), "A"), _put(Box(2, 2, 2), "B", (10, 0, 0))], "서브", at=(100, 0, 0)
    )
    path = _write(
        _group([sub, _put(Box(30, 30, 2), "Plate", (0, 0, -10))], "root"), tmp_path / "n.step"
    )
    rows, _ = _bodies(path)
    assert _names(rows) == ["A", "B", "Plate"]
    # 하위 조립을 X 100 에 놓았다 — 자식을 그대로 꺼내면 0 · 10 에 섰다(build123d 는 자리를
    # 조립에만 둔다).
    assert [row["centroid"][0] for row in rows] == [100.0, 110.0, 0.0]


def test_이름이_겹치면_뒤에_번호_비면_순번(tmp_path: Path) -> None:
    bolts = [_put(Cylinder(2, 10), "Bolt", (x, 0, 0)) for x in (0, 10, 20)]
    path = _write(
        _group([*bolts, _put(Box(40, 10, 2), "Plate", (10, 0, -6))], "root"),
        tmp_path / "d.step",
    )
    rows, _ = _bodies(path)
    assert _names(rows) == ["Bolt", "Bolt-2", "Bolt-3", "Plate"]
    assert [row["centroid"][0] for row in rows[:3]] == [0.0, 10.0, 20.0]

    # 이름 없는 부품 하나 — 옛 규칙은 조립 **전체**를 「전체」 하나로 뭉쳤다.
    named = _write(
        _group([_put(Box(10, 10, 10), "A"), _put(Box(5, 5, 5), "B", (20, 0, 0))], "root"),
        tmp_path / "e.step",
    )
    # 제품의 id · 이름을 둘 다 비운다 — 하나만 비우면 OCC 가 다른 쪽을 이름으로 쓴다.
    blank = tmp_path / "blank.step"
    blank.write_bytes(named.read_bytes().replace(b"PRODUCT('B','B'", b"PRODUCT('',''"))
    rows, _ = _bodies(blank)
    assert _names(rows) == ["A", "body_2"]
    old, _ = _bodies(blank, mode=None)
    assert _names(old) == ["전체"]


def test_솔리드와_서피스가_한_부품이면_둘_다_바디다(tmp_path: Path) -> None:
    mixed = Compound([Box(10, 10, 10), Face.make_rect(10, 10).moved(Location((0, 0, 20)))])
    rows, _ = _bodies(_write(mixed, tmp_path / "s.step"))
    assert [(row["kind"], row["volume"], row["area"]) for row in rows] == [
        ("solid", 1000.0, 600.0),
        ("sheet", 0.0, 100.0),
    ]


def test_닫힌_셸은_솔리드로_읽고_말한다(tmp_path: Path) -> None:
    rows, warnings = _bodies(_write(Shell(Box(10, 10, 10).faces()), tmp_path / "c.step"))
    assert [(row["name"], row["kind"], row["volume"]) for row in rows] == [
        ("전체", "solid", 1000.0)
    ]
    assert any("닫힌 셸 1개" in one for one in warnings)
    # 열린 셸은 셸 모델(시트) 그대로다.
    rows, _ = _bodies(_write(Shell(Box(10, 10, 10).faces()[:5]), tmp_path / "o.step"))
    assert [row["kind"] for row in rows] == ["sheet"]


def test_선뿐인_부품은_빼고_말한다(tmp_path: Path) -> None:
    axis = _put(Compound([Edge.make_line((0, 0, 0), (0, 0, 50))]), "Axis")
    path = _write(_group([_put(Box(10, 10, 10), "A"), axis], "root"), tmp_path / "w.step")
    rows, warnings = _bodies(path)
    # 남은 바디가 하나라 단품처럼 「전체」 다.
    assert [(row["name"], row["volume"]) for row in rows] == [("전체", 1000.0)]
    assert any("선 · 점뿐인 부품 1개(Axis)" in one for one in warnings)


def test_CP949_로_적힌_한글_이름을_읽는다(tmp_path: Path) -> None:
    path = _write(
        _group([_put(Box(10, 10, 10), "AAA"), _put(Box(5, 5, 5), "BBB", (20, 0, 0))], "root"),
        tmp_path / "k.step",
    )
    data = path.read_bytes()
    for old, new in ((b"'AAA'", "'블록'"), (b"'BBB'", "'핀'")):
        data = data.replace(old, new.encode("cp949"))
    path.write_bytes(data)
    rows, _ = _bodies(path)
    assert _names(rows) == ["블록", "핀"]
