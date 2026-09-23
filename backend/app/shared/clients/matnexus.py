"""물성 플랫폼(MatNexus) 클라이언트 — **우리가 대신 부른다.**

브라우저가 직접 못 부른다: 그쪽 CORS 는 자기 개발 주소만 허용한다(2026-09-24 소스 확인).
그리고 토큰을 화면에 내보낼 수도 없다. 그래서 이 서버가 중계한다.

## 늘 전역 재료만 묻는다

MatNexus 의 PAT 에는 **범위가 없다** — 그 계정의 권한 전부다. 서비스 계정 하나로 부르면서
작업공간 재료까지 보여 주면, 그쪽에서 나눠 둔 권한이 이쪽에서 무너진다. 그래서 `scope`
를 우리가 박는다(`global`). 사용자가 바꿀 수 있는 칸이 아니다.

## 값을 해석하지 않는다

받은 것을 **그대로** 나른다 — 항목 이름도 단위도 손대지 않는다. 「어느 것이 영률인가」 는
솔버를 아는 쪽(해석 플랫폼)의 일이고, 단위를 떼면 밀도에서 10¹² 배로 틀린다(그쪽 주석의
실측). 자세한 것은 `docs/해석-조건-설계.md` 6장.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings
from app.shared.errors import AppError, code

#: 우리가 절대 바꾸지 않는 질의 — 위 「전역 재료만」.
_SCOPE = "global"
_TIMEOUT = 15.0


class MatNexusUnavailable(RuntimeError):
    """못 닿았다 — 주소가 비었거나, 망이 끊겼거나, 토큰이 거절됐다.

    부르는 쪽은 이것을 받아 **올려 둔 카탈로그로 넘어간다.** 물성을 못 고른다고 작업이 멈추면
    안 된다."""


def configured() -> bool:
    settings = get_settings()
    return bool(settings.matnexus_base_url and settings.matnexus_token)


def missing() -> str:
    """**무엇이 비었는지 이름을 댄다.** 「설정이 없습니다」 로는 어느 칸을 채울지 모른다.

    실제로 겪었다(2026-09-24): 주소는 넣고 토큰만 비운 채로 화면을 열었더니 「주소가
    없습니다」 라고 말했다 — 맞는 칸을 놔두고 엉뚱한 데를 보게 만든다.
    """
    settings = get_settings()
    empty = []
    if not settings.matnexus_base_url:
        empty.append("MATNEXUS_BASE_URL(주소)")
    if not settings.matnexus_token:
        empty.append("MATNEXUS_TOKEN(토큰)")
    if not empty:
        return ""
    return f".env 의 {' · '.join(empty)} 가 비어 있습니다"


def _client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        base_url=settings.matnexus_base_url.rstrip("/"),
        timeout=_TIMEOUT,
        headers={"Authorization": f"Bearer {settings.matnexus_token}"},
    )


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    if not configured():
        raise MatNexusUnavailable(missing())
    try:
        with _client() as client:
            answer = client.get(path, params=params)
    except httpx.HTTPError as failure:
        raise MatNexusUnavailable(f"MatNexus 에 닿지 못했습니다: {failure}") from failure
    if answer.status_code == 401:
        raise MatNexusUnavailable("MatNexus 토큰이 거절됐습니다 — .env 의 MATNEXUS_TOKEN")
    if answer.status_code >= 400:
        # 그쪽 오류 문구를 그대로 옮긴다 — 우리가 다시 지어 내면 되짚을 수 없다.
        raise AppError(
            code("MATERIALS", 1),
            f"MatNexus 가 거절했습니다 (HTTP {answer.status_code}): {answer.text[:200]}",
        )
    return answer.json()


def search(query: str = "", family: str = "", limit: int = 30) -> list[dict[str, Any]]:
    """재료 목록 — 이름 · 별칭 · 번호로 찾는다.

    목록 응답에 `declared_properties` 가 통째로 들어 있어(그쪽 `MaterialOut`) 한 번 부르면
    화면이 밀도 · 푸아송비 · 탄성계수까지 바로 보여 준다. 두 번 부를 이유가 없다.
    """
    params: dict[str, Any] = {"scope": _SCOPE, "limit": limit}
    if query:
        params["q"] = query
    if family:
        params["family"] = family
    got = _get("/api/materials", params)
    items = got.get("items") if isinstance(got, dict) else got
    return list(items or [])


def get(material_id: str) -> dict[str, Any]:
    """재료 하나 — 통째로. 우리가 고르거나 줄이지 않는다."""
    got = _get(f"/api/materials/{material_id}")
    if not isinstance(got, dict):
        raise AppError(code("MATERIALS", 2), "MatNexus 의 답이 재료 한 벌이 아닙니다")
    return got


def ping() -> dict[str, Any]:
    """닿나. 관리자 화면이 「연결됨 · 몇 건」 을 보여 주는 데 쓴다."""
    if not configured():
        return {"configured": False, "ok": False, "detail": missing()}
    try:
        rows = search(limit=1)
    except MatNexusUnavailable as failure:
        return {"configured": True, "ok": False, "detail": str(failure)}
    except AppError as failure:
        return {"configured": True, "ok": False, "detail": failure.message}
    return {"configured": True, "ok": True, "detail": f"전역 재료 {len(rows)}건 이상"}
