"""구조 규칙을 시험이 지킨다. 지침 문서에만 적힌 규칙은 반드시 어긋난다."""

from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
MODULES = APP / "modules"
FRONTEND_MODULES = BACKEND.parent / "frontend" / "src" / "modules"

#: 백엔드에만 있는 모듈 — 화면이 없다. **사유와 함께** 적는다.
FRONTEND_MERGED: set[str] = {
    "audit",  # 접근 로그는 모델만 있다. 보는 화면이 생기면 여기서 뺀다.
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def test_모듈끼리_라우터를_직접_부르지_않는다() -> None:
    offenders: list[str] = []
    for path in MODULES.rglob("*.py"):
        module = path.relative_to(MODULES).parts[0]
        for name in _imports(path):
            if (
                name.startswith("app.modules.")
                and name.endswith(".routes")
                and name.split(".")[2] != module
            ):
                offenders.append(f"{path.relative_to(BACKEND)} -> {name}")
    assert not offenders, "모듈이 남의 라우터를 직접 부릅니다: " + ", ".join(offenders)


def test_shared_는_도메인_라우터를_모른다() -> None:
    for path in (APP / "shared").rglob("*.py"):
        for name in _imports(path):
            assert not name.endswith(".routes"), f"{path.name} 이 {name} 을 부릅니다"


def test_코어는_웹과_DB_를_모른다() -> None:
    """`app/core` 는 build123d 위의 순수 층이다. FastAPI · SQLAlchemy · 설정을 알면 CLI 와
    시험에서 코어만 따로 돌릴 수 없다."""
    banned = (
        "fastapi",
        "sqlalchemy",
        "starlette",
        "app.modules",
        "app.shared",
        "app.config",
        "app.database",
    )
    for path in (APP / "core").rglob("*.py"):
        for name in _imports(path):
            assert not name.startswith(banned), f"core/{path.name} 이 {name} 을 압니다"


def test_모든_모델이_all_models_에_있다() -> None:
    registered = (APP / "all_models.py").read_text(encoding="utf-8")
    missing: list[str] = []
    for path in MODULES.rglob("models.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            is_model = any(
                isinstance(base, ast.Name) and base.id == "Base" for base in node.bases
            )
            if is_model and not re.search(rf"\b{node.name}\b", registered):
                missing.append(node.name)
    assert not missing, f"all_models.py 에 없는 모델: {missing}"


def test_모듈_이름은_프론트와_같다() -> None:
    backend = {p.name for p in MODULES.iterdir() if p.is_dir() and not p.name.startswith("_")}
    frontend = {p.name for p in FRONTEND_MODULES.iterdir() if p.is_dir()}
    assert backend - FRONTEND_MERGED <= frontend, (
        f"프론트에 없는 백엔드 모듈: {backend - FRONTEND_MERGED - frontend}"
    )


def test_오류_코드를_손으로_잇지_않는다() -> None:
    """`errors.code()` 를 거쳐야 접두사를 바꿔도 전부 따라온다."""
    pattern = re.compile(r'["\']CCR-[A-Z]+-\d{4}["\']')
    for path in APP.rglob("*.py"):
        if path.name == "errors.py":
            continue
        found = pattern.findall(path.read_text(encoding="utf-8"))
        assert not found, f"{path.relative_to(BACKEND)} 에 손으로 이은 코드: {found}"
