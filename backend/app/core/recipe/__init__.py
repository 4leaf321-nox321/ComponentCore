"""레시피 — 형상을 **만드는 법**을 적은 연산 트리(JSON)와 그것을 build123d 로 만드는 평가기.

    {"version": 1, "nodes": [...], "result": "<node id>"}

손으로 그리는 편집기와 AI 가 같은 것을 만진다. 노드 종류와 칸은 `schema.py` 가 정본이고
(`describe()` 가 그것을 JSON 으로 내보내 편집기와 AI 프롬프트가 읽는다), 평가는 `evaluate.py`,
기본 도형 템플릿은 `templates.py` 다.

**웹 · DB 를 모른다.** `import_step` 노드의 artifact id 를 파일 경로로 푸는 일은 호출자가
넘기는 함수(`resolve_file`)가 한다.
"""

from app.core.recipe.evaluate import Evaluation, RecipeError, evaluate
from app.core.recipe.schema import Recipe, describe, parse

__all__ = ["Evaluation", "Recipe", "RecipeError", "describe", "evaluate", "parse"]
