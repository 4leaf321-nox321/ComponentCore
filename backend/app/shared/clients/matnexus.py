"""물성 플랫폼(MatNexus) 클라이언트 — **우리가 대신 부른다.**

브라우저가 직접 못 부른다: 그쪽 CORS 는 자기 개발 주소만 허용한다(2026-09-24 소스 확인).
그리고 토큰을 화면에 내보낼 수도 없다. 그래서 이 서버가 중계한다.

## 무엇이 보이나는 **그쪽이 정한다** (2026-09-24 권한 개편)

MatNexus 의 권한은 **부서 트리 + 소속**이다. 재료마다 `owner_workspace_name` 이 붙고, 계정은
제가 속한 부서의 것을 본다. 그리고 **PAT 에는 여전히 범위가 없다** — 토큰을 만들 때 정하는
것은 이름과 만료일뿐이다. 그러므로 **경계는 「이 토큰이 누구냐」 하나**이고, 우리가 질의로
권한을 흉내 낼 수 있는 자리는 없다.

전에는 `scope=global` 을 박아 두었다. 그 칸은 개편으로 **없어졌고**, MatNexus 는 모르는
질의를 조용히 무시하므로 그 뒤로는 **아무 필터도 아니었다**(실측 — 「전역 0건」 이던 화면이
개편 뒤 135건을 그대로 보여 줬다). 살아 있는 척하는 이름이 가장 나쁘다.

지금 하는 일은 셋이다:

- 그 계정이 보는 것을 **그대로** 보여 준다. 좁히고 싶으면 `MATNEXUS_WORKSPACE`(부서 slug).
- 재료마다 **어느 부서 것인지** 함께 나른다 — 두 부서에 같은 이름이 있을 수 있다.
- `ping()` 이 **어느 계정으로 붙었는지** 말한다. 시스템 관리자 토큰을 꽂아 두면 그쪽이 부서로
  나눠 둔 권한을 이쪽에서 통째로 우회하게 되는데, 그 사실은 **아무 데도 안 적히면** 아무도
  모른다.

## 값을 해석하지 않는다

받은 것을 **그대로** 나른다 — 항목 이름도 단위도 손대지 않는다. 「어느 것이 영률인가」 는
솔버를 아는 쪽(해석 플랫폼)의 일이고, 단위를 떼면 밀도에서 10¹² 배로 틀린다(그쪽 주석의
실측). 자세한 것은 `docs/해석-조건-설계.md` 6장.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.config import get_settings
from app.shared.errors import AppError, code

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


def classifications() -> list[dict[str, Any]]:
    """**무엇이 있나** — `[{family, category, count}]`. 그쪽이 이미 세어 준다.

    화면이 쪽(族) → 갈래 → 재료로 좁혀 들어가려면 **목록에 나온 것 말고 전부**가 필요하다.
    검색 결과에서 뽑아 만들면 「앞 서른 줄에 있는 쪽」 만 보이고, 사람은 나머지가 없는 줄
    안다. 개수가 함께 오므로 빈 갈래를 눌러 보게 하지도 않는다.
    """
    got = _get("/api/materials/classifications")
    return [one for one in (got or []) if isinstance(one, dict)]


def search(
    query: str = "", family: str = "", category: str = "", limit: int = 30
) -> list[dict[str, Any]]:
    """재료 목록 — 이름 · 별칭 · 번호로 찾는다.

    목록 응답에 `declared_properties` 가 통째로 들어 있어(그쪽 `MaterialOut`) 한 번 부르면
    화면이 밀도 · 푸아송비 · 탄성계수까지 바로 보여 준다. 두 번 부를 이유가 없다.
    """
    params: dict[str, Any] = {"limit": limit}
    if query:
        params["q"] = query
    if family:
        params["family"] = family
    if category:
        params["category"] = category
    if workspace := get_settings().matnexus_workspace:
        params["workspace"] = workspace
    got = _get("/api/materials", params)
    items = got.get("items") if isinstance(got, dict) else got
    return list(items or [])


#: `M-000123` 은 UUID 가 아니다 — 상세 API 는 UUID 만 받는다.
_UUID = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def get(material_id: str) -> dict[str, Any] | None:
    """재료 하나 — 통째로. 우리가 고르거나 줄이지 않는다.

    **번호(`M-000123`)와 UUID 는 다른 길이다**(2026-09-24 실측): 상세 API 는 UUID 만 받고,
    번호를 주면 `422 Input should be a valid UUID` 를 돌려준다. 우리가 손잡이로 삼는 것은
    번호이므로(이름은 바뀌어도 번호는 안 바뀐다) 번호일 때는 목록 API 의 `code` 로 찾는다.
    """
    if _UUID.match(material_id):
        got = _get(f"/api/materials/{material_id}")
        if not isinstance(got, dict):
            raise AppError(code("MATERIALS", 2), "MatNexus 의 답이 재료 한 벌이 아닙니다")
        return got
    params: dict[str, Any] = {"code": material_id, "limit": 1}
    if workspace := get_settings().matnexus_workspace:
        params["workspace"] = workspace
    rows = _get("/api/materials", params)
    items = rows.get("items") if isinstance(rows, dict) else rows
    first = (items or [None])[0]
    return first if isinstance(first, dict) else None


def whoami() -> dict[str, Any]:
    """이 토큰이 **누구냐.** 권한이 계정으로 정해지므로 이것이 곧 「무엇이 보이나」다.

    `is_system_admin` 이면 부서 구분 없이 전부 본다 — 읽기만 하는 연동에는 과하다. 그 사실을
    관리자 화면이 말할 수 있게 그대로 올린다."""
    got = _get("/api/auth/me")
    return got if isinstance(got, dict) else {}


def _account_line(me: dict[str, Any]) -> str:
    """사람이 읽을 한 줄 — 누구로 붙었고 어디를 보나."""
    who = me.get("display_name") or me.get("email") or "(이름 없음)"
    if me.get("is_system_admin"):
        return f"{who} — 시스템 관리자라 **모든 부서**가 보입니다"
    rooms = me.get("memberships") or []
    if not rooms:
        return f"{who} — 소속 부서가 없습니다(재료가 안 보일 수 있습니다)"
    names = ", ".join(str(one.get("name") or one.get("slug")) for one in rooms[:3])
    more = f" 외 {len(rooms) - 3}" if len(rooms) > 3 else ""
    return f"{who} — 부서 {len(rooms)}곳({names}{more})"


def ping() -> dict[str, Any]:
    """닿나 · **누구로** 닿았나 · 몇 건 보이나.

    「연결됨」 만으로는 부족하다는 것을 권한 개편에서 배웠다(2026-09-24): 붙기는 붙는데 계정이
    달라 아무것도 안 보이거나, 반대로 관리자 토큰이라 다 보이는 일이 생긴다. 둘 다 **화면에
    적히지 않으면 아무도 모른다.**
    """
    if not configured():
        return {"configured": False, "ok": False, "detail": missing()}
    settings = get_settings()
    try:
        me = whoami()
        # 몇 건이 보이나 — 한 줄만 받고 `total` 을 읽는다(135건을 끌어올 이유가 없다).
        params: dict[str, Any] = {"limit": 1}
        if settings.matnexus_workspace:
            params["workspace"] = settings.matnexus_workspace
        page = _get("/api/materials", params)
        seen = page.get("total") if isinstance(page, dict) else None
    except MatNexusUnavailable as failure:
        return {"configured": True, "ok": False, "detail": str(failure)}
    except AppError as failure:
        return {"configured": True, "ok": False, "detail": failure.message}
    room = settings.matnexus_workspace
    where = f"부서 「{room}」 로 좁힘" if room else "좁히지 않음"
    count = "?" if seen is None else seen
    return {
        "configured": True,
        "ok": True,
        "account": _account_line(me),
        # 권한이 과한지는 관리자가 판단한다 — 우리는 사실만 올린다.
        "system_admin": bool(me.get("is_system_admin")),
        "workspace": settings.matnexus_workspace,
        "materials": seen,
        "detail": f"{_account_line(me)} · {where} · 보이는 재료 {count}건",
    }
