"""치수 식 — 레시피를 **매개변수로** 그린다.

`params` 에 이름 붙인 치수를 두고, 어느 숫자 칸에든 `"=식"` 으로 쓴다:

    {"params": {"판_길이": 80, "두께": 10},
     "nodes": [{"id": "p", "op": "box", "length": "=판_길이", "height": "=두께",
                "width": "=판_길이 / 2"}]}

한 값을 고치면 그것을 쓰는 곳이 모두 따라온다 — 스케치 구속(치수 · 평행 · 접함)을 푸는
솔버는 아니지만, **지그가 필요로 하는 파라메트릭**(제품 치수가 바뀌면 지그가 따라 커짐)은
이것으로 된다. 「한쪽을 고정하고 반대쪽을 늘린다」 는 `align`(도형 · 기본 입체의 기준 자리)이
맡는다.

식은 **계산기**다. 이름 · 숫자 · 사칙연산 · 괄호 · 몇 가지 함수만 쓴다 — 임의 코드는 돌지
않는다(`eval` 을 쓰지 않는 까닭).
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable
from typing import Any

#: 식에서 부를 수 있는 함수.
FUNCTIONS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sqrt": math.sqrt,
    "sin": lambda deg: math.sin(math.radians(deg)),
    "cos": lambda deg: math.cos(math.radians(deg)),
    "tan": lambda deg: math.tan(math.radians(deg)),
    "hypot": math.hypot,
}
#: 식에서 쓸 수 있는 상수.
CONSTANTS: dict[str, float] = {"pi": math.pi}

_BINARY: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


class ExpressionError(ValueError):
    """식이 틀렸다 — 어디가 왜인지 사람 말로."""


def evaluate_expression(text: str, values: dict[str, float]) -> float:
    """`"=길이 / 2"` 를 숫자로. 앞의 `=` 는 있어도 없어도 된다."""
    body = text[1:] if text.startswith("=") else text
    try:
        tree = ast.parse(body, mode="eval")
    except SyntaxError as failure:
        raise ExpressionError(f"식 '{text}' 을 읽지 못했습니다") from failure
    return _node(tree.body, values, text)


def _node(node: ast.AST, values: dict[str, float], text: str) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise ExpressionError(f"식 '{text}': 숫자가 아닌 값이 있습니다")
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in values:
            return float(values[node.id])
        if node.id in CONSTANTS:
            return CONSTANTS[node.id]
        known = ", ".join(sorted(values)) or "(없음)"
        raise ExpressionError(f"식 '{text}': 모르는 이름 '{node.id}' — 아는 치수: {known}")
    if isinstance(node, ast.BinOp):
        handler = _BINARY.get(type(node.op))
        if handler is None:
            raise ExpressionError(f"식 '{text}': 쓸 수 없는 연산입니다")
        left = _node(node.left, values, text)
        right = _node(node.right, values, text)
        try:
            return float(handler(left, right))
        except ZeroDivisionError as failure:
            raise ExpressionError(f"식 '{text}': 0 으로 나눕니다") from failure
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        value = _node(node.operand, values, text)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            names = ", ".join(sorted(FUNCTIONS))
            raise ExpressionError(f"식 '{text}': 쓸 수 있는 함수는 {names} 뿐입니다")
        if node.keywords:
            raise ExpressionError(f"식 '{text}': 함수에 이름 붙인 값은 못 씁니다")
        return float(FUNCTIONS[node.func.id](*[_node(arg, values, text) for arg in node.args]))
    raise ExpressionError(f"식 '{text}': 치수 식에는 이름 · 숫자 · 사칙연산 · 괄호만 씁니다")


def resolve_params(raw: dict[str, Any]) -> dict[str, float]:
    """`params` 를 숫자로 푼다. 치수끼리 서로 가리켜도 된다(앞뒤 순서와 상관없이)."""
    given = raw.get("params") or {}
    if not isinstance(given, dict):
        raise ExpressionError("params: 이름과 값의 표여야 합니다")
    values: dict[str, float] = {}
    pending: dict[str, str] = {}
    for name, value in given.items():
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            raise ExpressionError(f"params.{name}: 숫자나 치수 식이어야 합니다")
        if isinstance(value, str):
            pending[name] = value
        else:
            values[name] = float(value)
    # 서로 가리키는 치수 — 풀리는 것부터 차례로. 한 바퀴에 하나도 못 풀면 고리다.
    while pending:
        progressed = False
        for name, text in list(pending.items()):
            try:
                values[name] = evaluate_expression(text, values)
            except ExpressionError:
                continue
            del pending[name]
            progressed = True
        if not progressed:
            # 마지막 오류를 그대로 보여 준다 — 「모르는 이름」 이면 오타, 아니면 고리다.
            name, text = next(iter(pending.items()))
            try:
                evaluate_expression(text, values)
            except ExpressionError as failure:
                raise ExpressionError(f"params.{name}: {failure}") from failure
            raise ExpressionError(f"params.{name}: 치수가 서로를 가리킵니다")
    return values


def resolve(raw: dict[str, Any]) -> dict[str, Any]:
    """레시피 전체에서 `"=식"` 을 숫자로 바꾼 **새 사본**을 돌려준다.

    `label` 처럼 글자를 담는 칸은 `=` 로 시작하지 않으니 건드리지 않는다."""
    values = resolve_params(raw)

    def walk(value: Any) -> Any:
        if isinstance(value, str):
            return evaluate_expression(value, values) if value.startswith("=") else value
        if isinstance(value, list):
            return [walk(one) for one in value]
        if isinstance(value, dict):
            return {key: walk(one) for key, one in value.items()}
        return value

    out = {key: walk(one) for key, one in raw.items() if key != "params"}
    out["params"] = values
    return out
