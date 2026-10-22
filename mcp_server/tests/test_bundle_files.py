"""MCP 서버가 불러들이는 옆 파일이 **번들 · 릴리스 점검 · 서버 설치** 세 자리에 다 실리나.

기준정보 도구(`ontology.py` · `ontology_links.py`)를 더하며 번들(`deploy/build_bundle.sh`)과
릴리스 점검(`release.yml`)은 고쳤는데, 서버에 까는 `deploy/deploy.sh` 는 `server.py` 를
이름으로 하나만 옮겼다 — 운영 MCP 가 `No module named 'ontology'` 로 뜨자마자 죽고
되살아나기를 되풀이했다(v0.16.0 ~ v0.16.4, 2026-10-23). 세 자리가 따로 적혀 있으니 옆 파일이
늘 때마다 여기서 맞춰 본다.

    cd mcp_server && ./venv/bin/python -m pytest tests
"""

from __future__ import annotations

import ast
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent


def _local_modules() -> set[str]:
    """server.py 에서 시작해 옆 파일끼리 불러들이는 것 전부(이름만)."""
    found: set[str] = set()
    todo = ["server"]
    while todo:
        name = todo.pop()
        tree = ast.parse((HERE / f"{name}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module.split(".")[0]]
            for one in names:
                if (HERE / f"{one}.py").exists() and one not in found and one != name:
                    found.add(one)
                    todo.append(one)
    return found | {"server"}


def test_옆_파일은_번들에_실린다() -> None:
    build = (ROOT / "deploy" / "build_bundle.sh").read_text(encoding="utf-8")
    missing = [
        one for one in sorted(_local_modules()) if f"cp mcp_server/{one}.py" not in build
    ]
    assert not missing, f"build_bundle.sh 가 안 싣는 MCP 파일: {missing}"


def test_옆_파일은_릴리스_점검이_본다() -> None:
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    missing = [
        one for one in sorted(_local_modules()) if f"mcp_server/{one}.py" not in release
    ]
    assert not missing, f"release.yml 「번들이 온전한가」 가 안 보는 MCP 파일: {missing}"


def test_서버_설치는_번들의_파이썬_파일을_전부_옮기고_뜨는지_먼저_본다() -> None:
    """이름을 하나씩 적으면 또 빠진다 — 번들에 든 `*.py` 를 전부 옮긴다. 옮긴 뒤 불러와 보고,
    안 되면 기동하지 않는다(systemd 가 되살리기를 되풀이하지 않게)."""
    deploy = (ROOT / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    assert '"$HERE"/mcp_server/*.py' in deploy
    assert '-c "import server"' in deploy
    assert deploy.index('-c "import server"') < deploy.index(
        'systemctl restart "$MCP_SERVICE_NAME"'
    )
