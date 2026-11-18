"""STEP 의 **한글 이름** — 쓸 때 깨지지 않는다(2026-11-18).

build123d 는 이름을 OCC 에 넘길 때 UTF-8 바이트를 Latin-1 글자로 읽어 두 번 인코딩했다 —
파일에 이미 깨져 들어가 되살릴 수 없었다. 그래서 우리 STEP 은 이름을 ASCII 로 바꿔(`slug`)
내보냈고, 내려받은 STEP 을 CAD 에서 열면 「센서 브래킷」 이 `body_1` 이었다. 이제 표준
이스케이프(ISO 10303-21 의 X2)로 쓴다. DOE 폴더는 해석 쪽과의 계약대로 ASCII(`step_product`)
그대로다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from build123d import Box, Compound, Location, Shape, import_step

from app.core import export
from app.core.recipe import parse, step_import
from app.core.recipe.schema import RecipeValidationError


def _assembly() -> tuple[Compound, list[Box]]:
    plate = Box(10, 10, 2)
    plate.label = "1번 판"
    bolt = Box(5, 5, 5).moved(Location((20, 0, 0)))
    bolt.label = "볼트 M6 (A'급)"
    plain = Box(3, 3, 3).moved(Location((40, 0, 0)))
    plain.label = "Plain"
    whole = Compound(children=[plate, bolt, plain])
    whole.label = "센서 조립"
    return whole, [plate, bolt, plain]


def test_한글_이름이_STEP_에_표준_이스케이프로_들어가고_되살아난다(tmp_path: Path) -> None:
    whole, parts = _assembly()
    path = export.write_step(whole, tmp_path / "k.step")
    data = path.read_bytes()
    assert data.isascii(), "파일은 ASCII — 이름은 X2 이스케이프"
    text = data.decode("ascii")
    assert "PRODUCT('1\\X2\\BC88\\X0\\ \\X2\\D310\\X0\\'" in text
    assert "M6 (A''\\X2\\AE09\\X0\\)" in text, "작은따옴표는 두 번"
    assert "CCSTEPNAME" not in text, "자리표가 남지 않는다"
    assert "PRODUCT('\\X2\\C13CC11C\\X0\\ \\X2\\C870B9BD\\X0\\'" in text, (
        "이어진 글자는 한 묶음"
    )
    # 읽으면 이름이 돌아온다 — 옛 규칙(`legacy`)은 build123d 처럼 공백 · 괄호를 `_` 로.
    names = [one.name for one in step_import.split(path)[0]]
    assert names == ["1번_판", "볼트_M6__A'급_", "Plain"]
    assert [child.label for child in import_step(path).children] == names
    # 넘겨준 형상의 이름표는 그대로다(잠시 바꿨다 되돌린다).
    assert [one.label for one in parts] == ["1번 판", "볼트 M6 (A'급)", "Plain"]
    assert whole.label == "센서 조립"


def test_DOE_폴더는_계약대로_ASCII_이름(tmp_path: Path) -> None:
    whole, _ = _assembly()
    path = export.write_step(whole, tmp_path / "doe.step", names="ascii")
    names = [one.name for one in step_import.split(path)[0]]
    assert names == ["1", "m6_a", "plain"], "topology.bodies[].step_product 와 같은 글자"


def test_아스키_이름은_그대로_쓴다(tmp_path: Path) -> None:
    plate = Box(10, 10, 2)
    plate.label = "Plate"
    pin = Box(1, 1, 5).moved(Location((10, 0, 0)))
    pin.label = "Pin"
    path = export.write_step(Compound(children=[plate, pin]), tmp_path / "a.step")
    assert [one.name for one in step_import.split(path)[0]] == ["Plate", "Pin"]


def test_이스케이프는_이어진_글자를_묶고_BMP_밖은_X4() -> None:
    assert export.step_text("센서") == "\\X2\\C13CC11C\\X0\\"
    assert export.step_text("a\\b'c") == "a\\\\b''c"
    assert export.step_text("판😀") == "\\X2\\D310\\X0\\\\X4\\0001F600\\X0\\"
    assert export.step_text("plain") == "plain"


def test_BMP_밖의_글자도_되살아난다(tmp_path: Path) -> None:
    one = Box(2, 2, 2)
    one.label = "판😀"
    other = Box(2, 2, 2).moved(Location((5, 0, 0)))
    other.label = "핀"
    path = export.write_step(Compound(children=[one, other]), tmp_path / "e.step")
    assert [child.label for child in import_step(path).children] == ["판😀", "핀"]


def _tricky(tmp_path: Path) -> Path:
    """이름이 까다롭고(공백 · 점 · 괄호 · 따옴표 · 겹침), 자리를 옮긴 하위 조립 · 멀티바디가
    있는 조립 — 쓰는 것은 우리 `write_step`(내려받은 STEP 을 다시 올리는 길)."""
    sub = Compound(
        children=[
            _named(Box(4, 4, 4), "센서 v1.2 (상)"),
            _named(Box(2, 2, 6), "핀", (5, 0, 0)),
        ]
    )
    sub.label = "하위 조립"
    sub = sub.moved(Location((40, 0, 0)))
    twin = Compound([Box(3, 3, 3), Box(3, 3, 3).moved(Location((0, 10, 0)))])  # 한 부품에 둘
    twin.label = "멀티 바디"
    whole = Compound(
        children=[
            _named(Box(10, 10, 2), "1번 판"),
            _named(Box(2, 2, 2), "Bolt", (20, 0, 0)),
            _named(Box(2, 2, 2), "Bolt", (25, 0, 0)),
            _named(Box(1, 1, 1), "A'급", (30, 0, 0)),
            twin.moved(Location((0, -20, 0))),
            sub,
        ]
    )
    whole.label = "조립"
    return export.write_step(whole, tmp_path / "tricky.step")


def _named(shape: Shape, label: str, at: tuple[float, float, float] = (0, 0, 0)) -> Shape:
    one = shape.moved(Location(at))
    one.label = label
    return one


def test_STEP_이름_그대로_읽으면_내보낸_이름이_돌아온다(tmp_path: Path) -> None:
    """2026-11-18 — 내보낼 때 이름이 그대로 나가게 되자, 다시 올리면 build123d 의 규칙(공백 ·
    점 · 괄호 → `_`) 때문에 이름이 달라졌다. 새로 올리는 STEP 은 `original` 로 읽는다."""
    path = _tricky(tmp_path)
    original = [one.name for one in step_import.split(path, "original")[0]]
    assert original == [
        "1번 판",
        "Bolt",
        "Bolt-2",
        "A'급",
        "멀티 바디-1",
        "멀티 바디-2",
        "센서 v1.2 (상)",
        "핀",
    ]
    legacy = [one.name for one in step_import.split(path)[0]]
    assert legacy[0] == "1번_판" and legacy[6] == "센서_v1_2__상_", (
        "이미 가져온 레시피는 그대로"
    )


def test_이름_그대로_읽어도_이름_말고는_build123d_와_같다(tmp_path: Path) -> None:
    """`_import_original` 은 build123d 의 `import_step` 을 따라 쓴 것 — build123d 를 올리면
    둘이 어긋나지 않았는지 여기서 본다(바디 수 · 부피 · 자리 · 시트)."""
    path = _tricky(tmp_path)
    original, notes_original = step_import.split(path, "original")
    legacy, notes_legacy = step_import.split(path)
    assert len(original) == len(legacy) and notes_original == notes_legacy
    rule = str.maketrans(" .()", "____")
    for one, other in zip(original, legacy, strict=True):
        assert one.name.translate(rule) == other.name
        assert one.sheet == other.sheet
        assert one.shape.volume == pytest.approx(other.shape.volume)
        assert tuple(one.shape.center()) == pytest.approx(
            tuple(other.shape.center()), abs=1e-6
        )
    # 하위 조립을 옮긴 만큼 그 안의 부품도 옮겨져 있다(위쪽 자리를 곱했다).
    moved = original[6].shape.center().X
    assert moved == pytest.approx(40)


def test_이름_그대로는_leaf_와만() -> None:
    with pytest.raises(RecipeValidationError, match="bodies='leaf'"):
        parse({"nodes": [{"id": "b", "op": "import_step", "file": "f", "names": "original"}]})


def test_앞뒤_공백은_지우고_공백뿐인_이름은_순번(tmp_path: Path) -> None:
    """해석 쪽은 바디 이름을 서로 견줘 짝짓는다 — 앞뒤 공백이 남으면 사람 눈에는 같아 보여도
    다른 이름이다(SimEngBay, 2026-11-18)."""
    whole = Compound(
        children=[
            _named(Box(2, 2, 2), "  판  "),
            _named(Box(2, 2, 2), "   ", (5, 0, 0)),
            _named(Box(2, 2, 2), "가운데  두 칸", (10, 0, 0)),
        ]
    )
    path = export.write_step(whole, tmp_path / "space.step")
    names = [one.name for one in step_import.split(path, "original")[0]]
    assert names == ["판", "body_2", "가운데  두 칸"]
