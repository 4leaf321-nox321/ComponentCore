<!-- version: 2026-09-18.1 -->
# AutoJigGenerator MCP 가이드

## overview

이 플랫폼에서 부품은 **레시피**(연산 트리 JSON)로 그린다. STEP 이 아니라 만드는 법을 저장하므로 치수를
바꿔 다시 만들 수 있고, 사람이 손으로 그린 것을 AI 가 고치고 그 반대도 된다.

하려는 일 → 부를 도구:

| 하려는 일 | 도구 |
| --- | --- |
| 무엇을 만들 수 있나 | `recipe_schema` (피처 종류 · 칸 · 내장 템플릿 넷 · 저장 템플릿 목록) |
| 저장 템플릿의 본문 | `template_recipe(id)` · 되풀이해 쓸 모양은 `save_template` 로 남긴다 |
| **내가 그린 것의 치수** | `recipe_geometry(recipe)` — 구멍 지름 · 중심 · 깊이, 면의 법선 · 넓이 |
| **제품을 기준으로 지그 그리기** | `part_geometry(part_id)` · `work_geometry(work_id)` — 치수표 + STEP id |
| **형상 여러 벌 만들기(DOE)** | `doe_preview` → `doe_create` → `doe_points` — 공유 폴더에 STEP 이 쌓인다 |
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
2. `recipe_check` 가 실패하면 메시지에 **어느 피처가 왜**인지 있다. 그것을 읽고 고쳐 다시 불러라.
   같은 실패를 세 번 반복하면 사용자에게 상황을 말하고 판단을 받아라.
3. 승격(카탈로그에 올리기)은 사람의 판단이다. 시키지 않았으면 하지 마라.
4. 치수 단위는 mm. 좌표계는 X 오른쪽 · Y 앞 · Z 위. 스케치 평면 XY 의 법선이 +Z 라 `extrude` 는
   위로 자란다.

## recipe

레시피: `{"version": 1, "nodes": [...], "result": "<node id>"}` — `result` 를 비우면 마지막 피처.
피처(`nodes` 의 항목)는 **순서대로** 평가되고 앞 피처만 id 로 가리킬 수 있다.

피처 종류(자세한 칸은 `recipe_schema`):
- 스케치 `sketch` — `plane` {name: XY|XZ|YZ|…, origin, (normal, x_dir)} 위의 2D 윤곽. `shapes` 는
  순서대로 더하거나(add) 빼는(cut) 도형: `rect`(width, height) · `circle`(radius) · `slot`(length,
  width, measure overall|centers — **도면이 주는 「중심 사이」 값이면 centers**) ·
  `regular_polygon`(radius, sides) · `polygon`(points) · `triangle`(a · b · c 와 A · B · C 중 셋,
  변은 하나 이상 — 「빗변 50 인 직각삼각형」 처럼 말로 주는 치수 그대로) · **`polyline`**(start,
  segments — 임의 윤곽) · `path`(start, segments, width,
  corners — 두께 있는 선: 리브 · 얇은 벽, 양 끝 둥글게) · `rounded_rect`(width, height, radius) ·
  `trapezoid`(width, height, left_angle, right_angle) · `ellipse`(x_radius, y_radius) ·
  `text`(text, size, bold — 각인은 cut 으로 얕게 돌출해서 뺀다). 각 도형은 `at` [x, y] · `rotation`.
  **구간(`segments`)의 한 칸은 다음 점 `to` 까지 어떻게 가는지다** — 아무것도 없으면 직선,
  `radius: R` 이면 그 반지름의 호(부호가 휘는 쪽: 양수 = 가는 방향의 **왼쪽**), `tangent: true` 면
  앞 구간에 **매끄럽게 이어지는 호**, `via: [x, y]` 면 그 점을 지나는 호.
  **글로 치수를 받았으면 `radius` · `tangent` 를 써라** — `via` 는 호 위의 점을 미리 계산해야 하고
  조금만 틀려도 엉뚱한 곡률이 된다(사람이 캔버스에서 찍을 때 쓰는 칸이다).
  `polyline` 의 `corner_radius` 는 모든 모서리를 둥글린다(호 `via` 와 함께는 못 쓴다).
  스케치의 `hull: true` 는 도형들을 **감싸는 볼록 윤곽** 하나로 만든다(흩어진 자리를 덮는 베이스
  판). 스케치의 `offset` 은 합친 윤곽을 밖(+)/안(−)으로 띄운다(2D 여유). `section`(target, plane,
  offset) 은 입체를 평면으로 자른 단면을 **스케치로** 준다 — 여유를 주고 돌출하면 포켓 윤곽.
- 입체 `extrude`(sketch, distance, direction normal|reverse|both, taper — 구배 도, 양수면 좁아짐,
  until distance|next|last + target — 대상의 다음/마지막 면까지; 관통 구멍은 last) ·
  `revolve`(sketch, axis, angle) · `sweep`(sketch, path [[x,y,z]…], smooth — 단면 스케치의 원점을
  경로 첫 점에 두라) · `helix`(sketch, radius, pitch, height, axis, at, lefthand — 스프링 · 나사산;
  단면은 XY 원점에 그리면 자동으로 시작점에 놓인다) · `loft`(sketches [2개 이상], ruled) · `box`(length, width, height, at) · `cylinder`(radius, height,
  axis, at) · `sphere`(radius, at) · `cone`(bottom_radius, top_radius, height, at) · `torus`
  (major_radius, minor_radius) · `wedge`(length, width, height, top_x_min/max, top_z_min/max —
  경사 블록) · `sheet_metal`(thickness, width, path [[x, y]…], plane, bend_radius, side left|right
  — **판금 절곡**: 옆에서 본 꺾은선대로 판을 접는다. 「2t 판, 30 올라가 20 꺾임, 폭 40, 굽힘 R3」
  이 그대로 칸이 된다. 꺾은선이 **폭의 가운데**에 오므로 구멍 자리는 평면 좌표 그대로 주면 된다.
  브래킷 · ㄱ자 앵글 · 덮개는 블록을 깎지 말고 이것으로) ·
  `import_step`(file — 사용자가 올린 STEP, 직접 만들지 않는다)
- 조합 `union`(targets) · `cut`(target, tools) · `intersect`(targets) · `split`(target, plane
  {name, origin | origin, normal}, keep top|bottom|both — 평면으로 자르기)
- 마감 `fillet`(target, edges, radius — 화면에서는 「블렌드」) · `chamfer`(target, edges, length —
  「챔퍼」) · `shell`(target, thickness, open top|bottom|none|{near}) · `offset`(target, amount,
  corners round|sharp — 전체를 두껍게/얇게. **제품에 여유를 주어 지그 포켓을 만들 때**) ·
  `draft`(target, faces sides|top|bottom|all|{near}, angle, neutral — 면을 기울여 구배) · `hole`(target, at [[x, y]…], kind simple|counterbore|
  countersink|tap, thread M3~M12 — 주면 지름 · 카운터 치수를 표에서, diameter, depth — 비우면 관통,
  counter_diameter, counter_depth, plane — 뚫을 면 {origin, normal}; 안 주면 윗면 +Z 에서 아래로)
  - `edges` 는 `all` · `vertical` · `horizontal` · `top` · `bottom` 또는 `{"near": [[x,y,z]…]}`
    (엣지 중점 위치로 고르기 — 사람이 3D 에서 누른 것. AI 는 이름 있는 선택자를 쓰는 편이 안전)
- 배치 `pattern`(source, kind linear|grid|circular, count, spacing | count_y+spacing_y | axis+angle)
  — 결과는 **복사본 묶음**
  이라 `cut` 의 tools 나 `union` 의 targets 로 쓴다 · `transform`(target, translate, rotate,
  scale) · `mirror`(target, plane, keep_original)

치수를 **변수로** 두고 싶을 때(파라메트릭 — 화면에서는 「변수」):
- 레시피에 `"params": {"판_길이": 80, "두께": 10}` 을 두고, **어느 숫자 칸에든**(피처의 칸도,
  스케치 도형의 width · radius · at 도) `"=판_길이 - 15"`
  처럼 쓴다. 하나를 고치면 그것을 쓰는 곳이 모두 따라온다 — 제품 치수가 바뀌면 지그도 따라 큰다.
  식에는 이름 · 숫자 · `+ - * / % **` · 괄호 · `abs min max round sqrt sin cos tan hypot` · `pi`
  만 쓴다(각도는 도 단위).
- **한쪽을 고정하고 반대쪽만 늘리려면** `align` 을 쓴다. 도형(`rect` · `circle` · `rounded_rect`
  · `slot` · `trapezoid` · `triangle` · `ellipse` · `text` · `regular_polygon`)은 `["min",
  "center"]` 처럼 두 축, 기본 입체(`box` · `cylinder` · `sphere` · `wedge`)는 세 축이다.
  `min` 이면 그 축의 **작은 쪽 끝이 `at` 에 고정**되고 커질 때 반대쪽으로만 자란다.
  예 — 왼쪽 끝과 바닥을 고정한 판: `{"op":"box","length":"=판_길이","width":50,"height":"=두께",
  "align":["min","center","min"]}`. (스케치 구속 솔버는 없다. 치수 이름 + 기준 자리로 푼다.)

**실험계획(DOE)** — 치수를 훑어 형상을 여러 벌 만들 때:
1. 레시피에 `params` 로 바꿀 치수를 둔다. **연결부를 이루는 칸이 그 치수를 쓰지 않으면 안 변한다.**
2. `doe_preview` 로 **개수를 먼저 센다** — 격자는 곱으로 늘어난다(인자 넷에 5단계면 625개,
   한 번에 200점까지).
3. `doe_create` — 점마다 형상을 만들어 **공유 폴더**에 `points/p0001.step` 과 `manifest.csv`
   (번호 · 치수 값 · 질량 · 크기)를 쓴다. 해석(ANSYS)은 그 폴더를 그대로 읽는다.
4. 목표가 **맞설 때**(두께를 키우면 공진은 올라가고 질량도 는다) `doe_tradeoff` 로 지지 않는
   점만 가린다 — 가중치로 한 값을 만들지 말고 표를 보여 주고 사람이 고르게 한다.
5. `doe_points` 로 표를 읽고 다음 범위를 좁힌다. 실패한 점은 사유가 적혀 있다 — 그 범위를 뺀다.
   LHS 는 `seed` 를 적어 두면 **같은 표**를 다시 만든다.
6. 변수끼리는 싸우지 않는다(칸 하나에 식 하나 — 과구속이 없다). 대신 값 조합이 형상을 깨면
   **그 점만** 실패로 남는다(사유가 적힌다) — 범위를 좁히거나 값을 바꾸라는 뜻이다.

지그를 **세트의 공진에 맞출 때**(부품을 세트에 넣은 것처럼 진동을 보려는 시험 지그):
1. 연결부(부품이 물리는 자리)는 **숫자로 못 박고**, 바꿔 갈 쪽만 `params` 로 둔다. 연결부를
   이루는 칸이 그 치수를 쓰지 않으면 **어떤 값에서도 안 변한다** — 그것이 이 설계의 규칙이다.
2. `beam_frequency(target_hz=…, length_mm=…, width_mm=…, added_mass_g=<부품 무게>)` 로 두께를
   되짚는다. **가늠값**이다 — 물림이 무르면 실제는 더 낮다. 사용자에게 그대로 전한다.
3. 그 두께로 레시피를 그리고 `sweep_parameter` 로 이웃 값들을 훑어 질량 · 관성과 함께 고른다
   (가공하기 좋은 두께로 고르는 일이 흔하다).
4. 마지막은 **실물로 재서** 맞춘다. 이 플랫폼에는 모달 해석이 없다 — 주파수는 가늠값이고,
   형상 · 질량 · 관성만이 정확한 값이다. 그 사실을 숨기지 않는다.

**지그는 두 길로 생긴다** — 어느 쪽인지 먼저 정한다:
- **만들어 준다**: `run_jig` — 제품 형상에서 받침 · 위치 핀 · 클램프를 규칙으로 배치한다.
  손잡이는 `jig_options`(판 두께 · 여유 · 핀 지름 …)뿐이고 **레시피가 아니라 변수를 못 심는다.**
- **그린다**: 레시피로 직접. 생성기가 만들 수 없는 지그(공진을 맞추는 시험 지그, 특수 치구)는
  이 길이다. 그리는 것이니 `params` 로 **변수를 심고 DOE 로 훑을 수 있다.** 다 그리면
  `promote_jig_recipe` 로 지그 카탈로그에 올린다(`part_id` 로 어느 부품의 지그인지 잇는다).

제품을 기준으로 **지그**를 그릴 때:
1. `list_parts` → `part_geometry(part_id)` — 크기 · 바닥 평면 · **구멍(지름 · 중심 · 깊이)** 을
   읽는다. 내 작업이라면 `work_geometry(work_id)`.
2. 자동으로 뽑으려면 `copy_part_to_work` → `run_jig`(옵션은 `jig_options`).
3. 손으로 그리려면 받은 `step_artifact_id` 로 제품을 불러와 쓴다:
   `{"op":"import_step","file":"<step_artifact_id>","id":"제품"}` →
   `{"op":"offset","target":"제품","amount":0.3,"id":"여유"}` →
   블록에서 `cut` 하면 **제품이 앉는 포켓**이 된다. 제품 구멍 자리에는 `cylinder`(align z=min)로
   핀을 세운다.
4. 그린 뒤 `recipe_geometry` 로 **확인한다** — 포켓 깊이 · 핀 지름이 뜻대로인지.

말로 받은 치수를 옮길 때:
- 호는 `radius` · `tangent`, 장공은 `slot.measure: "centers"`, 삼각형은 변 · 각 — **도면이 주는
  값을 그대로** 넣어라. 좌표로 환산하면서 틀리는 일이 제일 많다.
- 접어 만드는 것은 `sheet_metal`, 살을 붙이는 리브는 `path`(두께 있는 선), 감싸는 판은
  `sketch.hull`, 제품에 맞춘 포켓은 `section`(단면) + `offset`(여유) 또는 `offset` 뒤 `cut`.

자주 하는 실수:
- 결과가 스케치다 → `extrude` · `revolve` 로 입체를 만들어야 한다.
- 필렛 반지름이 인접 면보다 크다 → 줄이거나 `edges` 를 좁혀라(`vertical` 등).
- 뒤 피처를 가리켰다 → 순서를 바꿔라. id 가 겹친다 → 이름을 바꿔라.
- 면이 정확히 포개진 두 덩어리를 합쳤다 → 조금 겹치게 하라(예: 벽을 바닥판에 1mm 묻기).
- `cut` 이 전부를 지웠다 → 도구 위치를 확인하라.

템플릿에서 시작해 고치는 것이 가장 빠르다(내장은 `recipe_schema` 의 `templates`, 사람이 저장한
것은 `saved_templates` 의 id 로 `template_recipe`). 예 — 80×50×10 판에
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
   `recipe_schema` 의 템플릿에서. 치수만 바꿔 되풀이해 쓸 모양이면 `save_template` 로 남긴다
   (`shared: true` 면 공용 자리).
2. 레시피를 고친다 — **바꾸는 피처만** 손대고 나머지는 그대로 둔다. 새 피처는 끝에 붙이고 앞 피처를
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
