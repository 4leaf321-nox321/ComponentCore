"""공유 폴더로 보내기 — **읽는 쪽이 반쪽을 보지 않게**(`doe.export.publish`).

해석 쪽(SimEngBay)은 공유 폴더를 탐색기로 연다. 복사하는 동안 폴더가 보이면 STEP 이 덜 온 점을
「짝이 없다」 고 읽는다. 처음 보낼 때는 숨긴 이름에 다 쓴 뒤 이름을 바꾸고, 다시 보낼 때는 해석
쪽이 덧붙인 것을 지우지 않으며 표를 맨 나중에 바꿔 끼운다.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

import pytest

from app.modules.doe import export as files


def _study(folder: Path, points: int, manifest: str) -> Path:
    (folder / "points").mkdir(parents=True)
    for number in range(1, points + 1):
        (folder / "points" / f"p{number:04d}.step").write_text(f"step {number}")
    (folder / "manifest.csv").write_text(manifest)
    (folder / "study.json").write_text("{}")
    return folder


def _hidden(root: Path) -> list[str]:
    return sorted(one.name for one in root.rglob(".*"))


def test_처음_보낼_때는_다_쓴_뒤에_나타난다(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _study(tmp_path / "local", 2, "point\n1\n2\n")
    root = tmp_path / "공유"
    root.mkdir()
    target = root / "브래킷-1234abcd"
    seen: list[tuple[str, bool]] = []
    real = shutil.copytree

    def watching(src: Any, dst: Any, *args: Any, **kw: Any) -> Any:
        made = real(src, dst, *args, **kw)
        if Path(str(dst)).parent == root:
            # 복사가 끝난 순간에도 제 이름의 폴더는 아직 없다 — 숨긴 이름에 있다.
            seen.append((Path(str(dst)).name, target.exists()))
        return made

    monkeypatch.setattr(shutil, "copytree", watching)
    files.publish(source, target)
    ((name, existed),) = seen
    assert name.startswith(".") and files.PARTIAL in name and existed is False
    assert sorted(p.name for p in (target / "points").iterdir()) == [
        "p0001.step",
        "p0002.step",
    ]
    assert _hidden(root) == []


def test_복사가_도중에_실패하면_반쪽이_남지_않는다(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _study(tmp_path / "local", 2, "point\n")
    root = tmp_path / "공유"
    root.mkdir()
    real = shutil.copytree
    calls = {"n": 0}

    def flaky(src: str, dst: str, **kw: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError(28, "No space left on device")
        return shutil.copy2(src, dst)

    def failing(src: Any, dst: Any, *args: Any, **kw: Any) -> Any:
        return real(src, dst, copy_function=flaky)

    monkeypatch.setattr(shutil, "copytree", failing)
    with pytest.raises(OSError):
        files.publish(source, root / "브래킷-1234abcd")
    assert list(root.iterdir()) == []


def test_다시_보낼_때는_덧붙인_것을_지우지_않고_표를_바꿔_끼운다(tmp_path: Path) -> None:
    root = tmp_path / "공유"
    root.mkdir()
    target = root / "브래킷-1234abcd"
    files.publish(_study(tmp_path / "v1", 1, "point\n1\n"), target)
    (target / "results.csv").write_text("해석 쪽이 덧붙였다")

    # 점을 하나 더한 뒤 다시 보낸다.
    files.publish(_study(tmp_path / "v2", 2, "point\n1\n2\n"), target)
    assert (target / "manifest.csv").read_text() == "point\n1\n2\n"
    assert (target / "points" / "p0002.step").exists()
    assert (target / "results.csv").read_text() == "해석 쪽이 덧붙였다"
    assert _hidden(root) == []


def test_쓰다_멈춘_것은_하루가_지나면_치운다(tmp_path: Path) -> None:
    root = tmp_path / "공유"
    root.mkdir()
    stale = root / f".브래킷-1234abcd{files.PARTIAL}deadbeef"
    stale.mkdir()
    fresh = root / f".판-5678abcd{files.PARTIAL}cafef00d"
    fresh.mkdir()
    study = root / "브래킷-1234abcd"
    study.mkdir()
    stale_file = study / f".manifest.csv{files.PARTIAL}0badc0de"
    stale_file.write_text("x")
    old = time.time() - 2 * 86400
    os.utime(stale, (old, old))
    os.utime(stale_file, (old, old))

    removed = files.sweep_partials(root)
    assert sorted(Path(one).name for one in removed) == sorted([stale.name, stale_file.name])
    assert fresh.exists() and study.exists()
