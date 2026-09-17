"""작업 종류 레지스트리 — kind 이름 → 실행 함수.

**jobs 모듈은 도메인을 모른다.** 지그 모듈이 자기 종류를 등록하고(`app/handlers.py`), 워커와
API 는 이름으로 찾는다. jobs 가 jigs 를 import 하면 방향이 거꾸로 서고, 새 종류(cad · ai_cad)를
더할 때마다 jobs 를 고치게 된다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class Progress(Protocol):
    """실행 함수가 단계를 마칠 때마다 부른다 — 화면이 도는 동안 폴링해서 본다."""

    def __call__(self, name: str, millis: int, detail: str) -> None: ...


@dataclass
class ArtifactSpec:
    """실행 함수가 남긴 파일 하나. 서비스가 이것을 `Artifact` 행으로 만든다."""

    kind: str
    path: Path
    content_type: str


@dataclass
class Outcome:
    summary: dict[str, Any]
    artifacts: list[ArtifactSpec] = field(default_factory=list)


#: (input, options, out_dir, progress) → Outcome. 실패는 예외로 — 서비스가 status 와 error
#: 를 적는다.
Handler = Callable[[dict[str, Any], dict[str, Any], Path, Progress], Outcome]


class UserFacingError(Exception):
    """제품 쪽 사정(읽을 수 없는 STEP · 계획 불가)처럼 **사람이 읽고 고칠 수 있는** 실패.

    실행 함수가 이것을 던지면 메시지가 그대로 화면에 간다. 다른 예외는 코어의 버그로 보고
    트레이스백을 남기고 한 줄만 보여 준다.
    """


_handlers: dict[str, Handler] = {}


def register(kind: str, handler: Handler) -> None:
    if kind in _handlers and _handlers[kind] is not handler:
        raise RuntimeError(f"작업 종류가 두 번 등록됩니다: {kind}")
    _handlers[kind] = handler


def resolve(kind: str) -> Handler:
    try:
        return _handlers[kind]
    except KeyError:
        raise KeyError(f"등록되지 않은 작업 종류입니다: {kind}") from None


def known_kinds() -> tuple[str, ...]:
    return tuple(sorted(_handlers))
