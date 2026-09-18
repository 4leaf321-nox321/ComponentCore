"""치수 식과 기준 자리 — 「한쪽을 고정하고 반대쪽을 늘린다」 가 되는지."""

from __future__ import annotations

import pytest

from app.core.recipe import evaluate, parse
from app.core.recipe.params import ExpressionError, evaluate_expression, resolve_params
from app.core.recipe.schema import RecipeValidationError


def _plate(length: float) -> dict[str, object]:
    """왼쪽 끝(x=0)을 고정하고 오른쪽으로만 자라는 판 — 구멍은 오른쪽 끝에서 15."""
    return {
        "params": {"판_길이": length, "두께": 10},
        "nodes": [
            {
                "id": "p",
                "op": "box",
                "length": "=판_길이",
                "width": 50,
                "height": "=두께",
                "align": ["min", "center", "min"],
            },
            {
                "id": "h",
                "op": "hole",
                "target": "p",
                "at": [["=판_길이 - 15", 0]],
                "diameter": 6,
            },
        ],
    }


def test_치수_하나를_고치면_한쪽으로만_자란다() -> None:
    short = evaluate(parse(_plate(80))).summary()
    long = evaluate(parse(_plate(120))).summary()
    # 왼쪽 끝과 바닥은 그대로, 오른쪽만 늘어난다.
    assert short["bbox"]["min"] == long["bbox"]["min"] == (0.0, -25.0, 0.0)
    assert short["bbox"]["max"][0] == 80.0
    assert long["bbox"]["max"][0] == 120.0
    # 구멍도 따라 옮겨 간다 — 오른쪽 끝에서 늘 15.
    assert long["volume"] - short["volume"] == pytest.approx(40 * 50 * 10, rel=0.01)


def test_기준_자리를_안_주면_예전처럼_가운데() -> None:
    box = evaluate(
        parse({"nodes": [{"id": "b", "op": "box", "length": 40, "width": 30, "height": 20}]})
    )
    assert box.summary()["bbox"]["min"] == (-20.0, -15.0, -10.0)


def test_치수끼리_서로_가리켜도_풀린다() -> None:
    values = resolve_params({"params": {"w": 40, "h": "=w * 0.75", "r": "=min(w, h) / 4"}})
    assert values == {"w": 40.0, "h": 30.0, "r": 7.5}


def test_틀린_식은_어디가_왜인지_말한다() -> None:
    with pytest.raises(RecipeValidationError, match="모르는 이름 'aa'"):
        parse(
            {
                "params": {"a": 10},
                "nodes": [
                    {"id": "b", "op": "box", "length": "=aa", "width": 10, "height": 10}
                ],
            }
        )
    with pytest.raises(RecipeValidationError, match="0 으로 나눕니다"):
        parse(
            {
                "params": {"a": 0},
                "nodes": [
                    {"id": "b", "op": "box", "length": "=10/a", "width": 10, "height": 10}
                ],
            }
        )
    with pytest.raises(ExpressionError, match=r"서로를 가리킵니다|모르는 이름"):
        resolve_params({"params": {"a": "=b", "b": "=a"}})


def test_식은_계산기지_코드가_아니다() -> None:
    """임의 코드가 돌면 서버가 열린다 — 이름 · 숫자 · 사칙연산 · 흰 목록 함수뿐."""
    for danger in [
        "=__import__('os').system('ls')",
        "=open('/etc/passwd').read()",
        "=(1).__class__",
    ]:
        with pytest.raises(ExpressionError):
            evaluate_expression(danger, {})
    assert evaluate_expression("=sqrt(16) + max(1, 2) * 3", {}) == 10.0
    assert evaluate_expression("=지름 / 2", {"지름": 12}) == 6.0


def test_도형도_기준_자리를_가진다() -> None:
    """스케치도 같다 — 왼쪽 아래를 원점에 두고 그리면 치수를 도면처럼 읽는다."""
    got = evaluate(
        parse(
            {
                "params": {"w": 60},
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [
                            {
                                "type": "rect",
                                "width": "=w",
                                "height": 40,
                                "align": ["min", "min"],
                            }
                        ],
                    },
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
                ],
            }
        )
    )
    assert got.summary()["bbox"]["min"] == (0.0, 0.0, 0.0)
    assert got.summary()["bbox"]["max"] == (60.0, 40.0, 5.0)


def test_한글_이름을_쓴다() -> None:
    """치수 · 피처 이름에 한글을 쓸 수 있어야 레시피가 읽힌다 — 이 화면의 말은 한국어다."""
    got = evaluate(
        parse(
            {
                "params": {"판_길이": 40},
                "nodes": [
                    {
                        "id": "베이스",
                        "op": "box",
                        "length": "=판_길이",
                        "width": 20,
                        "height": 5,
                    }
                ],
            }
        )
    )
    assert got.nodes[0].id == "베이스"
    for bad in ["1핀", "핀 둘", "a/b"]:
        with pytest.raises(RecipeValidationError, match="쓸 수 없는 문자"):
            parse(
                {"nodes": [{"id": bad, "op": "box", "length": 10, "width": 10, "height": 10}]}
            )


def test_스케치_그림의_치수도_변수로_쓴다() -> None:
    """피처 칸만 되고 그림은 안 되면 「그림은 변수화가 안 되네」 가 된다 — 어느 칸이든 된다."""

    def plate(width: float) -> dict[str, object]:
        return {
            "params": {"판_폭": width, "구멍": 6},
            "nodes": [
                {
                    "id": "s",
                    "op": "sketch",
                    "shapes": [
                        {"type": "rect", "width": "=판_폭", "height": "=판_폭 * 0.6"},
                        {
                            "type": "circle",
                            "radius": "=구멍 / 2",
                            "at": ["=판_폭 / 2 - 10", 0],
                            "mode": "cut",
                        },
                    ],
                },
                {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
            ],
        }

    small = evaluate(parse(plate(80))).summary()
    big = evaluate(parse(plate(120))).summary()
    assert small["bbox"]["size"] == (80.0, 48.0, 5.0)
    assert big["bbox"]["size"] == (120.0, 72.0, 5.0)
    # 구멍도 변수를 따라 옮겨 갔다 — 두 판의 부피 차이가 사각형 차이와 같다.
    assert big["volume"] - small["volume"] == pytest.approx(
        120 * 72 * 5 - 80 * 48 * 5, rel=1e-6
    )
