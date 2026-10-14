"""부품 · 지그의 **「기준정보」 칸** — CompCore 에만 있는 온톨로지 도구(ADR 0008).

화면의 부품 · 지그 상세에 서는 그 칸과 같다(백엔드 `objects/source_links.py`): 부품(지그)에
닿는 관계 종류마다 한 줄 — 「적용 모델」 · 「서비스 부품」 · 「대상 모델」 처럼 — 과, 걸린 것,
이름에 든 낱말로 찾은 추천. 잇고 빼는 것은 **그 부품(지그)을 고칠 수 있는 사람**(주인 ·
관리자)이다.

SP 에서 옮긴 도구(`ontology.py`)와 같은 도우미 · 같은 등록을 쓴다 — 그 파일은 SP 에서 다시
만들므로 CompCore 의 것은 여기 따로 둔다.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from ontology import _delete, _get, _post, tool

#: 원 표의 키 → 백엔드 경로.
_BASES = {"part": "parts", "jig": "jigs"}


def _base(kind: str) -> str | None:
    return _BASES.get(kind.strip().lower())


@tool()
async def ontology_links(ctx: Context, kind: str, id: str) -> Any:
    """부품(`kind="part"`) · 지그(`kind="jig"`) 하나의 **「기준정보」 칸** — 관계 종류마다
    한 줄.

    줄마다 `label`(부품 쪽에서 본 말 — 「적용 모델」), `items`(걸린 것 — `link_id` 로 뺀다),
    `suggestions`(이름에 든 낱말로 찾은 후보), `single`(하나만 걸 수 있나), `other_types`
    (고를 수 있는 타입). `type_slug` 가 null 이면 이 원 표를 비추는 시스템 타입이 아직 없다 —
    관리자가 먼저 만든다(`ontology_import`).

    **추천은 짐작이다** — 잇기 전에 사람에게 보인다. 다른 것을 고르려면 `other_types` 의
    타입에서 `object_resolve` 로 이름을 해소해 `object_id` 를 얻는다."""
    base = _base(kind)
    if base is None:
        return {"error": f"kind 는 part · jig 중 하나입니다: {kind}"}
    return await _get(ctx, f"/api/{base}/{id}/ontology")


@tool()
async def ontology_link(
    ctx: Context, kind: str, id: str, relation: str, object_id: str
) -> Any:
    """부품 · 지그 하나에 기준정보 하나를 잇는다 — `relation` 은 `ontology_links` 의 줄
    (`rows[].relation`), `object_id` 는 그 줄의 `suggestions` 나 `object_resolve` 로 얻은 id.

    방향(기본 모델 → 부품)은 관계 정의대로 서버가 정한다. **그 부품을 고칠 수 있는
    사람만** 잇는다(주인 · 관리자) — 거절되면 사용자에게 그대로 전한다. 「하나만」 칸
    (`single`)이 이미 차 있으면 거절된다 — 먼저 `ontology_unlink`. 돌려주는 것은 고친 뒤의 칸
    전부다."""
    base = _base(kind)
    if base is None:
        return {"error": f"kind 는 part · jig 중 하나입니다: {kind}"}
    return await _post(
        ctx, f"/api/{base}/{id}/ontology/links", {"relation": relation, "object_id": object_id}
    )


@tool()
async def ontology_unlink(ctx: Context, kind: str, id: str, link_id: str) -> Any:
    """부품 · 지그 하나에 걸린 기준정보 하나를 뺀다 — `link_id` 는 `ontology_links` 의
    `rows[].items[].link_id`. 선 자체를 지운다(양쪽 상세에서 함께 사라진다). **사용자가 빼라고
    한 것만.** 돌려주는 것은 고친 뒤의 칸 전부다."""
    base = _base(kind)
    if base is None:
        return {"error": f"kind 는 part · jig 중 하나입니다: {kind}"}
    return await _delete(ctx, f"/api/{base}/{id}/ontology/links/{link_id}")
