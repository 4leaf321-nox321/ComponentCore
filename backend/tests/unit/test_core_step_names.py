"""STEP 의 **한글 이름** — 쓸 때 깨지지 않는다(2026-11-18).

build123d 는 이름을 OCC 에 넘길 때 UTF-8 바이트를 Latin-1 글자로 읽어 두 번 인코딩했다 —
파일에 이미 깨져 들어가 되살릴 수 없었다. 그래서 우리 STEP 은 이름을 ASCII 로 바꿔(`slug`)
내보냈고, 내려받은 STEP 을 CAD 에서 열면 「센서 브래킷」 이 `body_1` 이었다. 이제 표준
이스케이프(ISO 10303-21 의 X2)로 쓴다. DOE 폴더는 해석 쪽과의 계약대로 ASCII(`step_product`)
그대로다.
"""

from __future__ import annotations

from pathlib import Path

from build123d import Box, Compound, Location, import_step

from app.core import export
from app.core.recipe import step_import


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
    # 읽으면 이름이 돌아온다 — 공백 · 괄호의 `_` 는 build123d 가 읽을 때의 약속이다.
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
