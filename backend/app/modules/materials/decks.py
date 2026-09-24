"""솔버 카드덱을 **덤으로** 실어 보낸다.

## 왜

받는 쪽(SimEngBay)은 지금 `MP,EX,matid,…` 를 손으로 짠다. MatNexus 가 같은 것을 **더 완전하게**
만들어 준다 — CTE · 비열 · 전도율 · 소성 표까지, 그리고 **단위계를 골라** 뽑으므로 덱 머리에
단위가 박힌다(`! Consistent units: tonne, mm, s, MPa`). 손으로 짜다 틀릴 자리가 없어진다.

## 그래도 중립이 정본이다

덱은 **솔버별**이라 담는 순간 솔버를 고르는 것이다. 우리 계약은 솔버를 모르는 것이고 받는
쪽이 하나가 아니므로, 덱은 payload 를 **대신하지 않고 옆에 붙는다**. 어느 형식을 담을지는
사람이나 오케스트레이터가 고른다(`Material.deck_formats`).

## 언제 뽑나 — 내보낼 때

고를 때가 아니라 **내보낼 때** 뽑는다. 한 해석에 재료가 여럿이면 덱 안의 재료 번호(`mid`)가
서로 달라야 하는데, 그 번호는 한 벌이 다 모여야 정해지기 때문이다. 이미 뽑아 둔 글월의
번호를 나중에 고치려면 솔버 덱 글월을 우리가 다시 써야 하고, 그건 틀릴 자리다.

## 못 뽑아도 폴더는 나간다

덱은 덤이다. MatNexus 에 못 닿거나 그 재료에 카드가 없으면 **그 사실을 적고 넘어간다** —
중립 payload 는 이미 폴더에 있고, 그것이 계약이다.
"""

from __future__ import annotations

from typing import Any

from app.shared.clients import matnexus

#: 형식별 파일 확장자. 모르는 형식은 `.txt` — 이름을 지어내는 것보다 낫다.
_EXTENSION: dict[str, str] = {
    "ansys": "dat",
    "abaqus": "inp",
    "abaqus_viscoelastic": "inp",
    "abaqus_hyperelastic": "inp",
    "abaqus_rate": "inp",
    "abaqus_lve": "inp",
    "abaqus_temperature": "inp",
    "abaqus_viscosity": "inp",
    "nastran": "bdf",
    "nastran_temp": "bdf",
    "nastran_thermal": "bdf",
    "optistruct": "fem",
    "optistruct_temp": "fem",
    "optistruct_thermal": "fem",
    "dyna": "k",
    "dyna_elastic": "k",
    "dyna_thermal": "k",
    "dyna_viscoelastic": "k",
    "dyna_johnson_cook": "k",
    "lsdyna": "k",
    "lsdyna_thermal": "k",
    "openradioss": "rad",
    "openradioss_thermal": "rad",
    "json": "json",
}


def extension(deck_format: str) -> str:
    return _EXTENSION.get(deck_format, "txt")


def _card_for(material_id: str, deck_format: str) -> str | None:
    """이 재료로 그 형식을 낼 **카드**. 없으면 None(낼 수 없다는 뜻)."""
    for one in matnexus.deck_formats(material_id):
        if one.get("key") == deck_format and one.get("ready") and one.get("card_id"):
            return str(one["card_id"])
    return None


def build(material: dict[str, Any], system: str, mid: int) -> dict[str, Any]:
    """재료 하나의 덱들. `{"decks": [...], "notes": [...]}`.

    **실패를 조용히 삼키지 않는다** — 못 뽑았으면 왜인지 `notes` 에 적어 폴더에 남긴다.
    그래야 받는 쪽이 「덱이 없네, 왜지」 를 우리에게 묻지 않는다.
    """
    formats = [str(one) for one in (material.get("deck_formats") or []) if one]
    if not formats:
        return {"decks": [], "notes": []}

    ref = material.get("ref") or {}
    material_id = str(ref.get("material_id") or "")
    source = str(ref.get("source") or "")
    label = str(ref.get("name") or ref.get("code") or "물성")
    if not material_id:
        return {"decks": [], "notes": [f"{label}: 그쪽 id 를 몰라 덱을 못 뽑았습니다"]}

    decks: list[dict[str, Any]] = []
    notes: list[str] = []
    for deck_format in formats:
        try:
            if "literature" in source:
                # 문헌은 카드가 없다 — 카탈로그가 바로 만들어 준다(형식은 둘뿐).
                got = matnexus.catalog_deck(material_id, deck_format, system, mid)
                text, name = str(got.get("text") or ""), str(got.get("filename") or "")
                for why in got.get("skipped") or []:
                    notes.append(f"{label}/{deck_format}: {why.get('why') or why}")
            else:
                card = _card_for(material_id, deck_format)
                if card is None:
                    notes.append(
                        f"{label}/{deck_format}: 이 재료로는 낼 수 없습니다 "
                        "(확정 카드가 없거나 그 형식이 요구하는 값이 빠졌습니다)"
                    )
                    continue
                text, name = matnexus.card_deck(card, deck_format, system, mid), ""
        except Exception as failure:  # 덤이 본체를 막지 않는다.
            # 중립 payload 는 이미 폴더에 있다 — 그것이 계약이다.
            notes.append(f"{label}/{deck_format}: {failure}")
            continue
        if not text.strip():
            notes.append(f"{label}/{deck_format}: 빈 덱이 왔습니다")
            continue
        decks.append(
            {
                "format": deck_format,
                "units": system,
                "mid": mid,
                "filename": name or f"{deck_format}.{extension(deck_format)}",
                "text": text,
            }
        )
    return {"decks": decks, "notes": notes}
