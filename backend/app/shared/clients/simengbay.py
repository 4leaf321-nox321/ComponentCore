"""해석 쪽(SimEngBay) 클라이언트 — 받는 쪽 **능력표**를 받아 온다(`docs/해석-확장-설계.md`
5장).

부르는 것은 하나다: `GET /api/simulations/capabilities`(SimEngBay v0.36.0 부터). 늘 배열이고
솔버마다 한 장이다. 관리자가 「갱신」 을 누를 때만 부른다 — 저장 · 내보내기는 받아 둔
복사본으로 거른다(`modules/server/capabilities_store`). 받는 쪽이 꺼져 있다고 저장이 막히면
안 된다.

## 인증 — 읽기 범위 PAT

`Authorization: Bearer <토큰>`, 토큰은 「<설치 이름>_pat_」 로 시작하고 범위 `read` 가 있어야
한다. 오류 봉투는 `{"error": {"code": "SEB-AUTH-0101", "message", "request_id", "details"}}`
이고 코드의 앞(접두사)은 설치마다 다를 수 있어 **끝(`AUTH-0101`)으로 견준다**(SimEngBay,
2026-11-27).

- 401 `AUTH-0100` — 머리가 가지 않았다(이쪽은 늘 붙이므로 중간의 프록시가 지웠을 때).
- 401 `AUTH-0101` — 토큰이 틀림 · 만료 · 폐기, **또는 토큰 주인 계정이 막힘**. 그쪽은 셋을
  가리지 않는다(공격자에게 힌트를 주지 않으려고). 계정이 막힌 것은 토큰을 바꿔도 안 풀린다.
- 403 `AUTH-0104` — 토큰에 읽기 범위가 없다. 범위를 고쳐 다시 발급한다.

받은 것을 **그대로** 나른다 — 모양을 보는 것은 코어(`conditions.capabilities.read`)의 일이다.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings

_TIMEOUT = 15.0
PATH = "/api/simulations/capabilities"


class SimEngBayUnavailable(RuntimeError):
    """능력표를 받지 못했다 — 주소 · 토큰이 비었거나, 망이 끊겼거나, 그쪽이 거절했다.
    부르는 쪽은 복사본을 그대로 두고 까닭만 말한다."""


def configured() -> bool:
    settings = get_settings()
    return bool(settings.simengbay_base_url and settings.simengbay_token)


def missing() -> str:
    """**무엇이 비었는지 이름을 댄다** — 주소만 넣고 토큰을 비웠을 때 「주소가 없다」 로 읽히지
    않게(MatNexus 에서 겪었다)."""
    settings = get_settings()
    empty = []
    if not settings.simengbay_base_url:
        empty.append("SIMENGBAY_BASE_URL(주소)")
    if not settings.simengbay_token:
        empty.append("SIMENGBAY_TOKEN(토큰)")
    if not empty:
        return ""
    return f".env에 {', '.join(empty)} 값이 설정되지 않았습니다."


def base_url() -> str:
    """바탕 주소 — 끝의 `/` 를 뗀다. 화면에 보여도 되는 값이다(토큰은 머리로만 간다)."""
    return get_settings().simengbay_base_url.rstrip("/")


def _error_code(answer: httpx.Response) -> str:
    try:
        body = answer.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    return str(error.get("code") or "") if isinstance(error, dict) else ""


def refused(status: int, error_code: str) -> str:
    """그쪽이 거절한 까닭을 **고칠 것**으로 — 관리 화면에 그대로 띄운다."""
    if status == 401 and error_code.endswith("AUTH-0100"):
        return (
            "SimEngBay가 인증 정보를 받지 못했습니다(AUTH-0100). 중간의 프록시가 "
            "Authorization 헤더를 전달하는지 확인하십시오."
        )
    if status == 401:
        return (
            "SimEngBay가 토큰을 거부했습니다. 토큰이 맞지 않거나 만료 또는 폐기되었습니다. "
            ".env의 SIMENGBAY_TOKEN을 새 토큰으로 바꾸고, 그래도 해결되지 않으면 SimEngBay "
            "관리자에게 토큰 주인 계정의 상태를 확인하십시오."
        )
    if status == 403:
        return (
            "SimEngBay 토큰에 읽기 범위(read)가 없습니다. SimEngBay에서 읽기 범위로 토큰을 "
            "다시 발급해 .env의 SIMENGBAY_TOKEN에 넣으십시오."
        )
    if status == 404:
        return (
            "SimEngBay에서 능력표 주소를 찾지 못했습니다(HTTP 404). SIMENGBAY_BASE_URL에 "
            "접두어(예: /simengbay)까지 넣었는지, SimEngBay가 v0.36.0 이상인지 확인하십시오."
        )
    detail = f", {error_code}" if error_code else ""
    return f"SimEngBay가 요청을 거부했습니다(HTTP {status}{detail})."


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=base_url(),
        timeout=_TIMEOUT,
        headers={"Authorization": f"Bearer {get_settings().simengbay_token}"},
    )


def capabilities() -> Any:
    """능력표 전부(`?solver=` 없이 — 설치가 받는 솔버마다 한 장)."""
    if not configured():
        raise SimEngBayUnavailable(missing())
    try:
        with _client() as client:
            answer = client.get(PATH)
    except httpx.HTTPError as failure:
        raise SimEngBayUnavailable(
            f"SimEngBay에 연결하지 못했습니다({type(failure).__name__}). "
            "SIMENGBAY_BASE_URL과 방화벽을 확인하십시오."
        ) from failure
    if answer.status_code >= 400:
        raise SimEngBayUnavailable(refused(answer.status_code, _error_code(answer)))
    try:
        return answer.json()
    except ValueError as failure:
        raise SimEngBayUnavailable(
            "SimEngBay의 응답이 JSON이 아닙니다. SIMENGBAY_BASE_URL이 SimEngBay를 "
            "가리키는지 확인하십시오."
        ) from failure
