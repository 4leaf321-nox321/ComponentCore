"""백엔드가 **이 토큰을 거절했다**(401) — 도구 결과가 아니라 예외로 올린다.

`server.py` 와 `ontology.py`(SP 에서 옮긴 것 — `port_from_sp.py` 가 다시 만든다)가 함께
쓴다. 규칙과 문구는 Standard Platform `mcp_server/server.py` 의 `BackendUnauthorized` ·
`_rejected`(SP ADR 0028 결정 12)와 같다 — 세 플랫폼(SP · CompCore · SimEngBay)이 같은 꼴로
실패해야 HWAX 게이트웨이가 한 규칙으로 다시 받는다(2026-10-23, SimEngBay 의 요청).
"""

from __future__ import annotations

import httpx


class BackendUnauthorized(Exception):
    """백엔드가 이 토큰을 거절했다(401).

    HWAX 게이트웨이는 사람마다 그 사람의 위임 토큰(CompCore `POST /api/auth/sso` 가 2일짜리로
    낸다)을 들고 있다가, 도구 결과가 이 꼴일 때만 **새로 받아 한 번 다시 부른다**:

        ^Error executing tool \\S+: (GET|POST|PUT|PATCH|DELETE) \\S+ → HTTP 401

    FastMCP 는 도구에서 난 예외를 `Error executing tool <이름>: <예외 문구>` 로 감싸 오류
    결과로 낸다 — 그래서 문구를 `<METHOD> <경로> → HTTP 401: <서버의 말>` 로 지으면 그
    정규식에 맞는다. 401 을 다른 오류처럼 `{"error": "[…] …"}` 결과로 돌려주던 때는 그 신호가
    안 닿아, 회수 · 만료된 토큰으로 다음 갱신까지 「토큰이 유효하지 않습니다」 만 받았다.
    401 은 인증에서 끊긴 것이라 도구는 아무것도 안 했다 — 다시 불러도 두 번 실행되지 않는다.
    **401 밖(403 · 404 · 409 · 422 · 500)은 결과로 둔다** — 다시 부르면 쓰기가 두 번 돈다.

    게이트웨이를 안 거치는 사람(자기 토큰으로 직접)에게도 같은 문구가 간다 — 무엇을 부르다 왜
    막혔는지가 그대로 읽힌다(토큰을 새로 만들면 된다).
    """


def rejected(response: httpx.Response) -> BackendUnauthorized:
    """`<METHOD> <경로> → HTTP 401: <서버의 말>` — 경로는 물음표 앞까지(게이트웨이의
    `\\S+`)."""
    try:
        method = response.request.method
        path = response.request.url.raw_path.decode("ascii", "replace").split("?", 1)[0]
    except RuntimeError:  # 요청 없이 만든 응답(시험) — 실제 호출에는 늘 있다
        method, path = "GET", "/"
    said = "토큰이 없거나 유효하지 않습니다"
    try:
        body = response.json()
    except ValueError:
        body = None
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        said = f"[{error.get('code') or 401}] {error.get('message') or said}"
    return BackendUnauthorized(f"{method} {path} → HTTP 401: {said}")
