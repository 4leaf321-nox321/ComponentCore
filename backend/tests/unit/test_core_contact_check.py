"""조립의 맞닿은 쌍과 접촉 — 빠뜨린 접촉 · 본딩 채우기 · 모달에서 접촉이 풀리는 법.

판 · 받침 · 덮개(위로 쌓음)로, CalculiX 로 실측한 꼴(2026-11-16) 그대로: 판-받침 본딩만 걸고
받침-덮개 접촉을 빠뜨리면 덮개가 떠 모드 여섯이 모두 0 Hz 였는데 아무도 말하지 않았다.
"""

from __future__ import annotations

from typing import Any

from build123d import Box, Cylinder, Part, Pos

from app.core import contact_check, quality
from app.core.recipe.query import body_parts, select_features


def _put(shape: Any, label: str, at: tuple[float, float, float] = (0, 0, 0)) -> Any:
    one = shape.moved(Pos(*at))
    one.label = label
    return one


def _stack() -> Part:
    return Part(
        children=[
            _put(Box(60, 40, 3), "판", (0, 0, 1.5)),
            _put(Box(20, 20, 10), "받침", (0, 0, 8)),
            _put(Box(30, 20, 2), "덮개", (0, 0, 14)),
        ]
    )


def _face(name: str, body: str, z: int) -> dict[str, Any]:
    select = {"what": "faces", "body": body, "kind": "plane", "normal": [0, 0, z]}
    return {"name": name, "entity": "face", "select": select}


def _conditions(*contacts: dict[str, Any], analysis: str = "modal") -> dict[str, Any]:
    return {
        "named_selections": [
            _face("판 바닥", "판", -1),
            _face("판 윗면", "판", 1),
            _face("받침 아랫면", "받침", -1),
            _face("받침 윗면", "받침", 1),
            _face("덮개 아랫면", "덮개", -1),
        ],
        "constraints": [{"name": "고정", "type": "fixed_support", "on": "판 바닥"}],
        "contacts": list(contacts),
        "analysis": {"type": analysis},
    }


BOND = {"name": "판-받침", "type": "bonded", "source": "받침 아랫면", "target": "판 윗면"}


def test_맞닿은_쌍은_넓이와_자리를_잰다_모서리만_닿은_것은_빼고() -> None:
    found = quality.inspect(_stack())["touching"]
    assert [(one["a"], one["b"], one["area"], one["at"]) for one in found] == [
        ("판", "받침", 400.0, [0.0, 0.0, 3.0]),
        ("받침", "덮개", 400.0, [0.0, 0.0, 13.0]),
    ]
    # 판 모서리에 모서리로만 닿은 상자 — 거리는 0 이지만 넓이가 없어 접촉을 걸 쌍이 아니다.
    corner = Part(
        children=[
            _put(Box(60, 40, 3), "판", (0, 0, 1.5)),
            _put(Box(10, 10, 3), "귀", (35, 25, 1.5)),
        ]
    )
    assert quality.inspect(corner)["touching"] == []
    # 구멍에 낀 핀 — 곡면도 넓이로 잰다(2π · 4 · 10).
    pin = Part(
        children=[_put(Box(40, 40, 10) - Cylinder(4, 10), "블록"), _put(Cylinder(4, 20), "핀")]
    )
    (one,) = quality.inspect(pin)["touching"]
    assert one["area"] == 251.3274


def test_빠뜨린_접촉을_자리와_함께_말하고_본딩으로_채울_것을_낸다() -> None:
    shape = _stack()
    got = contact_check.report(shape, _conditions(BOND))
    assert [(one["a"], one["b"]) for one in got["missing"]] == [("받침", "덮개")]
    (warn,) = [one for one in got["notes"] if one["level"] == "warn"]
    assert (
        "접촉 미정의: 인접 바디 ‘받침’ · ‘덮개’" in warn["text"]
        and "(0, 0, 13)" in warn["text"]
    )
    # 채울 것 — 화면이 누른 면에 붙이는 것과 같은 규칙(바디 + 방향)으로 양쪽 그룹과 본딩 하나.
    proposal = got["proposal"]
    assert [one["name"] for one in proposal["named_selections"]] == [
        "받침-덮개 접촉면(받침)",
        "받침-덮개 접촉면(덮개)",
    ]
    assert proposal["named_selections"][0]["select"]["body"] == "받침"
    (contact,) = proposal["contacts"]
    assert contact["type"] == "bonded" and {contact["source"], contact["target"]} == {
        "받침-덮개 접촉면(받침)",
        "받침-덮개 접촉면(덮개)",
    }
    # 채우면 빠진 쌍이 없다.
    filled = _conditions(BOND, contact)
    filled["named_selections"] += proposal["named_selections"]
    again = contact_check.report(shape, filled)
    assert again["missing"] == [] and not any(one["level"] == "warn" for one in again["notes"])


def _pinned() -> Part:
    """구멍(반지름 4)에 꼭 맞는 머리 달린 핀 — 판의 구멍 원통과 핀 몸통이 **같은 자리 · 같은
    중심**이고, 판 윗면 · 머리 아랫면은 중심이 구멍 속이다(볼트 예압 픽스처의 아래판 ↔
    볼트)."""
    pin = Cylinder(4, 10) + Cylinder(7, 3).moved(Pos(0, 0, 6.5))
    return Part(children=[_put(Box(60, 40, 10) - Cylinder(4, 10), "판"), _put(pin, "핀")])


def test_채울_본딩의_면_규칙은_맞닿은_그_면을_집는다() -> None:
    """접촉 자동 찾기는 면의 **중심**으로 규칙을 짓는다. 중심이 구멍 속인 면, 딴 바디의 면과
    자리가 같은 면은 「중심에 가장 가까운 면」 이 딴 면이었다 — 볼트 픽스처의 면 28 개 중 4
    개의 본딩이 딴 면에 걸렸고(v0.31.0 은 7 개) 아무도 말하지 않았다(2026-11-26)."""
    shape = _pinned()
    parts = body_parts(shape)
    index = {face: at for at, face in enumerate(shape.faces())}
    got = contact_check.proposal(shape, [("판", "핀")], set())
    rules = {one["name"]: one["select"] for one in got["named_selections"]}
    for mine, other in (("판", "핀"), ("핀", "판")):
        touching = contact_check._touching_faces(parts[mine], parts[other])
        assert len(touching) == 2, mine  # 원통 하나 + 평면 하나
        wanted = sorted(index[face] for face, _ in touching)
        rule = rules[f"판-핀 접촉면({mine})"]
        assert sorted(one["index"] for one in select_features(shape, rule)["items"]) == wanted


def test_면_그룹이_잘못_걸린_접촉을_말한다() -> None:
    """본딩 면이 딴 면에 걸려도 아무도 말하지 않았다(2026-11-26). 떨어진 면끼리면 받는 쪽이
    못 묶고, 같은 면을 양쪽에 두면 면이 제 자신과 묶일 뿐이다. 떨어지지 않는 접촉이면 경고,
    하중으로 닿을 수 있는 접촉이 처음에 떨어진 것은 알림."""
    shape = _stack()
    wrong = {"name": "판-덮개", "type": "bonded", "source": "덮개 아랫면", "target": "판 바닥"}
    gap = {**wrong, "name": "판-덮개 마찰", "type": "frictional", "friction": 0.2}
    itself = {**BOND, "name": "판-판", "type": "frictional", "source": "판 윗면"}
    got = contact_check.report(shape, _conditions(BOND, wrong, gap, itself, analysis="static"))
    notes = [one for one in got["notes"] if one["where"].startswith("접촉 ")]
    assert [(one["where"], one["level"]) for one in notes] == [
        ("접촉 ‘판-덮개’", "warn"),
        ("접촉 ‘판-덮개 마찰’", "info"),
        ("접촉 ‘판-판’", "warn"),
    ]
    assert "‘덮개 아랫면’" in notes[0]["text"] and "맞닿아 있지 않습니다" in notes[0]["text"]
    assert "처음에 떨어져 있습니다" in notes[1]["text"]
    assert "같은 면을 가리킵니다" in notes[2]["text"]
    # 점 파일의 경고는 틀린 것만 — 알림은 빠진다.
    found = contact_check.misplaced(
        shape, [BOND, wrong, gap, itself], _conditions()["named_selections"]
    )
    assert [(one["name"], one["problem"]) for one in found] == [
        ("판-덮개", "apart"),
        ("판-덮개 마찰", "apart"),
        ("판-판", "same_face"),
    ]
    assert [line.split(":")[0] for line in contact_check.misplaced_warnings(found)] == [
        "접촉 ‘판-덮개’",
        "접촉 ‘판-판’",
    ]


def test_옛_자동_규칙이_딴_바디의_같은_자리_면을_집은_본딩을_말한다() -> None:
    """v0.31.0 의 접촉 자동 찾기가 지은 꼴 — 핀 쪽 그룹이 판의 구멍 원통을 집었다. 겹친
    넓이로는 맞닿아 보여(같은 면이다) 「같은 면」 으로 잡는다."""
    shape = _pinned()
    hole = {"what": "faces", "body": "판", "kind": "cylinder"}
    selections = [
        {"name": "판 구멍", "entity": "face", "select": hole},
        # 「핀」 이라고 지었지만 판의 구멍을 집는다 — 같은 자리 · 같은 중심.
        {"name": "핀 몸통", "entity": "face", "select": {**hole, "near": [-4.0, 0.0, 0.0]}},
    ]
    bond = {"name": "판-핀", "type": "bonded", "source": "핀 몸통", "target": "판 구멍"}
    (one,) = contact_check.misplaced(shape, [bond], selections)
    assert one["problem"] == "same_face"


def test_접촉을_하나도_안_걸면_경고가_아니라_알림이다() -> None:
    """받는 쪽이 맞닿은 면을 모두 붙여 푼다 — 위험한 것은 일부만 걸었을 때다."""
    got = contact_check.report(_stack(), _conditions())
    assert len(got["missing"]) == 2
    assert [one["level"] for one in got["notes"]] == ["info"]


def test_모달에서_접촉이_풀리는_법과_미끄럼으로만_이어진_바디() -> None:
    shape = _stack()
    slide = {
        "name": "받침-덮개",
        "type": "frictionless",
        "source": "덮개 아랫면",
        "target": "받침 윗면",
    }
    notes = contact_check.report(shape, _conditions(BOND, slide))["notes"]
    texts = {one["where"]: one for one in notes}
    assert "법선 방향만 구속되어" in texts["접촉 ‘받침-덮개’"]["text"]
    assert texts["바디 ‘덮개’"]["level"] == "warn" and "0 Hz" in texts["바디 ‘덮개’"]["text"]

    rough = {**slide, "type": "frictional", "friction": 0.2}
    notes = contact_check.report(shape, _conditions(BOND, rough))["notes"]
    assert any("본딩으로 처리됩니다" in one["text"] for one in notes)
    assert not any(one["where"] == "바디 ‘덮개’" for one in notes)

    # 정적이면 접촉 안내는 없다(비선형 접촉이 그대로 든다).
    static = contact_check.report(shape, _conditions(BOND, slide, analysis="static"))["notes"]
    assert static == []


def test_해석에서_뺀_파트는_접촉이_없어도_말하지_않는다() -> None:
    """「조건_강체지그_쉘브래킷」 의 명판 — 해석 제외라 이을 것이 없다."""
    conditions = _conditions(BOND)
    conditions["body_settings"] = [{"name": "덮개", "suppressed": True}]
    got = contact_check.report(_stack(), conditions)
    assert got["missing"] == [] and got["proposal"]["contacts"] == []
