<!-- version: 2026-09-18.1 -->
# AutoJigGenerator MCP 가이드

## overview

이 플랫폼에서 부품은 **레시피**(연산 트리 JSON)로 그린다. STEP 이 아니라 만드는 법을 저장하므로 치수를
바꿔 다시 만들 수 있고, 사람이 손으로 그린 것을 AI 가 고치고 그 반대도 된다.

하려는 일 → 부를 도구:

| 하려는 일 | 도구 |
| --- | --- |
| 무엇을 만들 수 있나 | `recipe_schema` (노드 종류 · 칸 · 내장 템플릿 넷 · 사용자가 저장한 템플릿) |
| 레시피가 맞나, 만들어지나 | `recipe_check` — **저장 전에 반드시** |
| 새 부품 시작 | `create_work(name, recipe)` |
| 있는 부품 고치기 | `get_work` 로 레시피를 받아 고쳐 `save_version` |
| 되돌리기 | `list_versions` → `restore_version` |
| 지그 만들기 | `run_jig(work_id, options)` → 계획 · 간섭이 돌아온다 |
| 남에게 내놓기 | `promote_part` · `promote_jig` — **사용자가 시킬 때만** |
| 남의 것 가져오기 | `list_parts` → `copy_part_to_work` |

기본 습관:
1. 저장은 늘 **사용자의 내 작업**에 새 버전으로 들어간다. 옛 버전은 남는다. 그러니 겁내지 말고
   저장하되, `note` 에 무엇을 바꿨는지 한 줄 적어라 — 사람이 이력에서 그것을 읽는다.
2. `recipe_check` 가 실패하면 메시지에 **어느 노드가 왜**인지 있다. 그것을 읽고 고쳐 다시 불러라.
   같은 실패를 세 번 반복하면 사용자에게 상황을 말하고 판단을 받아라.
3. 승격(카탈로그에 올리기)은 사람의 판단이다. 시키지 않았으면 하지 마라.
4. 치수 단위는 mm. 좌표계는 X 오른쪽 · Y 앞 · Z 위. 스케치 평면 XY 의 법선이 +Z 라 `extrude` 는
   위로 자란다.

## recipe

레시피: `{"version": 1, "nodes": [...], "result": "<node id>"}` — `result` 를 비우면 마지막 노드.
노드는 **순서대로** 평가되고 앞 노드만 id 로 가리킬 수 있다.

노드 종류(자세한 칸은 `recipe_schema`):
- 스케치 `sketch` — `plane` {name: XY|XZ|YZ|…, origin, (normal, x_dir)} 위의 2D 윤곽. `shapes` 는
  순서대로 더하거나(add) 빼는(cut) 도형: `rect`(width, height) · `circle`(radius) · `slot`(length,
  width) · `regular_polygon`(radius, sides) · `polygon`(points). 각 도형은 `at` [x, y] · `rotation`.
- 입체 `extrude`(sketch, distance, direction normal|reverse|both) · `revolve`(sketch, axis, angle) ·
  `box`(length, width, height, at) · `cylinder`(radius, height, axis, at) · `import_step`(file —
  사용자가 올린 STEP, 직접 만들지 않는다)
- 조합 `union`(targets) · `cut`(target, tools) · `intersect`(targets)
- 마감 `fillet`(target, edges, radius) · `chamfer`(target, edges, length) · `hole`(target, at [[x, y]…],
  diameter, depth — 비우면 관통; 위 +Z 에서 아래로)
  - `edges` 는 `all` · `vertical` · `horizontal` · `top` · `bottom` 또는 `{"near": [[x,y,z]…]}`
    (엣지 중점 위치로 고르기 — 사람이 3D 에서 누른 것. AI 는 이름 있는 선택자를 쓰는 편이 안전)
- 배치 `pattern`(source, kind linear|circular, count, spacing | axis+angle) — 결과는 **복사본 묶음**
  이라 `cut` 의 tools 나 `union` 의 targets 로 쓴다 · `transform`(target, translate, rotate) ·
  `mirror`(target, plane, keep_original)

자주 하는 실수:
- 결과가 스케치다 → `extrude` · `revolve` 로 입체를 만들어야 한다.
- 필렛 반지름이 인접 면보다 크다 → 줄이거나 `edges` 를 좁혀라(`vertical` 등).
- 뒤 노드를 가리켰다 → 순서를 바꿔라. id 가 겹친다 → 이름을 바꿔라.
- 면이 정확히 포개진 두 덩어리를 합쳤다 → 조금 겹치게 하라(예: 벽을 바닥판에 1mm 묻기).
- `cut` 이 전부를 지웠다 → 도구 위치를 확인하라.

템플릿(`recipe_schema` 의 templates)에서 시작해 고치는 것이 가장 빠르다. 예 — 80×50×10 판에
모서리 Ø6 구멍 넷:

```json
{"nodes": [
  {"id": "base", "op": "sketch", "shapes": [{"type": "rect", "width": 80, "height": 50}]},
  {"id": "plate", "op": "extrude", "sketch": "base", "distance": 10},
  {"id": "holes", "op": "hole", "target": "plate",
   "at": [[-30, -15], [30, -15], [30, 15], [-30, 15]], "diameter": 6}
]}
```

## workflow

1. `get_work(work_id)` 로 지금 레시피와 평가 요약(크기 · 부피 · 면 수)을 받는다. 새로 만들 때는
   `recipe_schema` 의 템플릿에서.
2. 레시피를 고친다 — **바꾸는 노드만** 손대고 나머지는 그대로 둔다. 새 노드는 끝에 붙이고 앞 노드를
   가리킨다.
3. `recipe_check(recipe)` — 통과할 때까지. 요약의 bbox · volume 이 의도와 맞는지 본다.
4. `save_version(work_id, recipe, note)` — 평가가 끝나면 요약이 돌아온다.
5. 지그가 필요하면 `run_jig(work_id, options)`. 간섭이 있으면 결과의 `plan.notes` 와
   `interference.items` 를 읽고 (a) 옵션(판 여유 · 받침 수 · 클램프 수) 또는 (b) 부품을 고쳐 다시.
6. 사용자가 시키면 `promote_part` / `promote_jig`.

## jig

`run_jig` 옵션(`jig_options` 로 기본값): `plate_margin`(제품 둘레 판 여유) · `plate_thickness` ·
`support_count`(3 또는 4) · `support_diameter` · `support_height` · `clamp_count` ·
`clamp_pad_diameter` · `locator_pin_clearance`.

결과 `summary`:
- `plan.supports` 받침 위치, `plan.locators` 핀(구멍이 있을 때) 또는 레스트(옆면), `plan.clamps`
  패드 · 기둥 위치, `plan.notes` 계획이 스스로 남긴 말(「구멍이 없어 옆면 레스트로」 등)
- `interference.ok` 와 `items` — 겹친 부품 쌍과 부피(mm³). 0 이어야 정상.
- `stages` 단계별 시간.

지그가 잘 잡히는 부품: 평평한 바닥, 바닥으로 열린 수직 구멍 둘(핀 로케이터), 평평한 윗면(클램프
패드). 바닥이 곡면이면 계획이 실패한다.
