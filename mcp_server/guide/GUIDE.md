<!-- version: 2026-10-03.1 -->
# CompCore MCP 가이드

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
| **해석 조건 붙이기** | `conditions_schema` → `recipe_find` · `recipe_selectors` → `set_conditions` — `get_guide("conditions")` |
| **물성 붙이기** | `material_search` → `material_get`(→ `condition_item`) · `recipe_bodies` → `set_conditions` |
| **형상 여러 벌 만들기(DOE)** | `doe_preview` → `doe_create` → `doe_points` → `doe_export` — 공유 폴더에 STEP 이 쌓인다 |
| 레시피가 맞나, 만들어지나 | `recipe_check` — **저장 전에 반드시** |
| 새 부품 시작 | `create_work(name, recipe)` |
| 있는 부품 고치기 | `get_work` 로 레시피를 받아 고쳐 `save_version` |
| 되돌리기 | `list_versions` → `restore_version` |
| 부품에서 지그 생성 | `jig_preview(source, options)` 로 계획을 보고 → `run_jig` → 지그 작업이 생긴다 |
| 남에게 내놓기 | `promote_part` · `promote_jig_recipe` — **사용자가 시킬 때만** |
| 남의 것 가져오기 | `list_parts` → `copy_part_to_work` |
| 폴더로 나눠 보기 | `list_works` · `list_parts` · `list_jigs` 의 `folder`(그 아래까지). 만들 때 `create_work(folder)` · `save_template(folder)` |
| 이름으로 찾기 | `search("브래킷")` — 내 작업 · 공용 부품 · 지그 · 템플릿 한꺼번에 |

기본 습관:
1. 저장은 늘 **사용자의 내 작업**에 새 버전으로 들어간다. 옛 버전은 남는다. 그러니 겁내지 말고
   저장하되, `note` 에 무엇을 바꿨는지 한 줄 적어라 — 사람이 이력에서 그것을 읽는다.
2. `recipe_check` 가 실패하면 메시지에 **어느 피처가 왜**인지 있다. 그것을 읽고 고쳐 다시 불러라.
   같은 실패를 세 번 반복하면 사용자에게 상황을 말하고 판단을 받아라.
3. 승격(카탈로그에 올리기)은 사람의 판단이다. 시키지 않았으면 하지 마라.
4. 치수 단위는 mm. 좌표계는 X 오른쪽 · Y 앞 · Z 위. 스케치 평면 XY 의 법선이 +Z 라 `extrude` 는
   위로 자란다.
5. **눈으로 확인한다** — `recipe_check` 를 통과했어도 저장 전에 `recipe_views` 로 그림(등각 ·
   정면 · 윗면 · 우측)을 보고 뜻대로인지 본다. 구멍이 엉뚱한 자리에, 필렛이 다른 엣지에 간 것은
   검사로는 안 잡힌다.
6. **좌표를 짐작하지 않는다** — 엣지 · 면 자리는 `recipe_find` 로 묻고(`near` · `plane` 에 그대로
   쓴다), 거리 · 두께 · 각도는 `recipe_measure` 로 잰다.
7. **고칠 때는 `patch_work`** — 레시피 전체를 되보내지 말고 연산 몇 개(set_param · set_field ·
   add_node …)로. 크고 실수가 적다. 조립에서 놓는 것은 `place_on` / `assemble_jig_on_part`.

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
  경사 블록) · **표준 부품** `bolt`(at=머리가 앉는 점, nominal, length, head hex|socket, washer,
  down) · `pin`(at=밑면 중심, diameter, length, chamfer) · `standoff`(at=밑면 중심, outer, hole,
  height) · `nut`(at, thread M3~M12, direction) · `washer`(at, thread, direction) ·
  `bearing`(at, designation 608 · 625 · 626 · 6000~6005 · 6200~6205, direction) ·
  `spring`(at, wire, diameter — 평균 지름, length — 자유 길이, coils, direction) ·
  `bracket`(at — 두 프로파일 면이 만나는 안쪽 모서리, size 20|30|40|45, legs [[다리1], [다리2]]
  — 알루미늄 프로파일 코너 브래킷) — 볼트 · 핀 · 스페이서 · 너트를 원통으로 손수 그리지 않는다.
  **구멍에 볼트를 꽂을 때는 `fasten`**(target, holes — 구멍 면 질의 예 `{"kind":"cylinder",
  "radius":3.3}`, part bolt|nut|washer|pin, thread — 비우면 구멍 지름으로(여유 구멍 · 탭 드릴),
  length — 비우면 구멍 깊이, head socket|hex, washer, side top|bottom): 구멍마다 그 축에 놓는다
  — 볼트는 머리가 side 끝(카운터보어면 턱)에, 너트 · 와셔는 side 끝에서 바깥으로, 핀은 반대쪽
  끝에서 들어가 지름만큼 나온다. 좌표가 없어 DOE 가 구멍을 옮겨도 따라간다 · `sheet_metal`(thickness, width, path [[x, y]…], plane, bend_radius, side left|right
  — **판금 절곡**: 옆에서 본 꺾은선대로 판을 접는다. 「2t 판, 30 올라가 20 꺾임, 폭 40, 굽힘 R3」
  이 그대로 칸이 된다. 꺾은선이 **폭의 가운데**에 오므로 구멍 자리는 평면 좌표 그대로 주면 된다.
  브래킷 · ㄱ자 앵글 · 덮개는 블록을 깎지 말고 이것으로) ·
  `bend`(target, bends [{at, radius, toward up|down, until angle|end, angle}…], along [x,y,z],
  k_factor — **펼친 판을 굽힌다**: 평평한 판(두께 한결같은 입체 — `box` 나 스케치 `extrude` 에
  구멍 · 노치를 낸 것)을 굽힘선에서 반지름 R 로 접거나 원통에 감는다. `at` 은 **펼친 판**에서
  `along` 방향 좌표(along 이 X 면 x 값)이고 굽힘선은 along 에 수직이다. 여러 굽힘은 `at` 이 커지는
  순서로, 굽힘마다 그 뒤쪽 판이 따라 돈다. `until: end` 는 남은 판을 끝까지 감는다(마지막 굽힘만).
  `toward: up` 은 판의 위쪽(누운 판이면 +Z). 굽힘 구간에 걸린 구멍도 같이 휘고, 굽힘면은
  원통면(안쪽 R · 바깥 R+t)이라 `kind: cylinder` 로 고를 수 있다. 펼친 길이는 중립면
  (`k_factor`, 기본 0.5 — 안쪽 면에서 두께의 몇 할)에서 보존된다. 포켓 · 단차 · 위아래 모서리
  필렛 · 모따기가 있는 판은 거절한다 — 그런 것은 굽힌 **뒤에**. 굽힘선은 모두 평행이다(한 노드
  안에서). 예 — 100 길이 판을 x=40 에서 R5 로 90° 세우기:
  `{"op":"bend","target":"판","bends":[{"at":40,"radius":5,"angle":90}]}`) ·
  `frame`(profile, paths [[[x,y,z]…]…], corner miter|butt|none, meet butt|overlap, roll,
  separate — **구조
  프레임**: 단면을 경로의 부재마다 세운다. profile 은 `{"type":"t_slot","size":20|30|40|45}`
  (알루미늄 프로파일, 근사 단면) · `square_tube`(width, thickness) · `rect_tube`(width, height,
  thickness) · `round_tube`(diameter, thickness) · `round_bar`(diameter) · `flat_bar`(width,
  height) · `angle`(width, height, thickness) · `channel`(width, height, thickness) ·
  `h_beam`(width, height, web, flange). 경로 하나는 점 목록 — 점 사이가 부재 하나, 마지막 점이
  처음 점과 같으면 닫힌 틀. 단면 가운데가 경로 위, 단면 위쪽이 +Z(서 있는 부재는 +X) — roll 로
  돌린다. corner: miter 45° 맞대기 · butt 앞 부재가 지나가고 뒤 부재가 그 옆면에서 시작(직각에서
  꼭 맞는다) · none 겹치기. **다른 경로에 닿는 열린 끝**(기둥 → 틀)은 meet 가 정한다 — butt
  (기본)면 그 부재의 옆면까지 맞춘다: 기둥 경로를 틀의 **중심선 점까지** 그리면 틀 밑면에서
  멈춘다(조금 모자라도 단면 안이면 늘인다), overlap 이면 그대로 겹친다. 기본은 한 덩어리,
  separate 면 부재마다 따로(볼트 조립 프레임을 부재별로 해석). **절단 목록**은
  `recipe_cutlist(recipe, node_id)` — 부재마다 자를 길이 · 끝의 각(0 = 직각) · 부피. 예 — 600 x 400 탁자 틀:
  `{"op":"frame","profile":{"type":"t_slot","size":40},"corner":"butt",
  "paths":[[[0,0,0],[600,0,0],[600,400,0],[0,400,0],[0,0,0]]]}`) ·
  `import_step`(file — 사용자가 올린 STEP, 직접 만들지 않는다)
- 조합 `union`(targets) · `cut`(target, tools) · `intersect`(targets) · `split`(target, plane
  {name, origin | origin, normal}, keep top|bottom|both — 평면으로 자르기)
- 마감 `fillet`(target, edges, radius, radius_end · start — 화면에서는 「블렌드」. radius_end 를
  주면 엣지를 따라 반지름이 radius → radius_end 로 변하고, start 점에 가까운 끝이 radius) ·
  `chamfer`(target, edges, length, length2 | angle, reference — 「챔퍼」. length2 는 비대칭 두
  거리, angle 은 거리-각도(도). length 는 기준면 쪽 — reference {"near": [[x,y,z]]} 로 고르고,
  비우면 두 면 중 위(+Z)를 보는 면) · `shell`(target, thickness, open top|bottom|none|{near}) · `offset`(target, amount,
  corners round|sharp — 전체를 두껍게/얇게. **제품에 여유를 주어 지그 포켓을 만들 때**) ·
  `draft`(target, faces sides|top|bottom|all|{near}, angle, neutral — 면을 기울여 구배) · `hole`(target, at [[x, y]…], kind simple|counterbore|
  countersink|tap, thread M3~M12 — 주면 지름 · 카운터 치수를 표에서, diameter, depth — 비우면 관통,
  counter_diameter, counter_depth, plane — 뚫을 면 {origin, normal}; 안 주면 윗면 +Z 에서 아래로)
  · `defeature`(target, faces {"near": [[x,y,z]…]}, holes_below, fillets_below — **면을 지우고
  메운다**: 지름이 holes_below 보다 작은 구멍(카운터보어 · 카운터싱크 포함), 반지름이
  fillets_below 보다 작은 필렛, 고른 면을 지우고 이웃 면을 늘려 막는다. 해석용 단순화와 피처
  이력이 없는 `import_step` 제품을 고칠 때. 이어진 필렛이 끝면 둘레를 다 두르면 메울 수 없어
  남기고 요약의 `warnings` 에 적는다 — 그때는 기준을 줄이거나 faces 로 골라 지운다)
- 영역 `imprint`(target — **접촉 자리 새기기**: 조립(group)의 바디끼리 닿는 자리를 서로의 면에
  새겨 나눈다. 판 위의 블록이면 판 윗면이 닿는 자리와 나머지로 갈려 접촉면 짝이 넓이 · 자리까지
  같아진다. 닿는 자리마다 태그 `받침판/블록`(받침판 쪽 면) · `블록/받침판`(블록 쪽 면) — 접촉
  조건은 `source`·`target` 선택 그룹을 `{"what":"faces","tag":"블록/받침판"}` ·
  `{"what":"faces","tag":"받침판/블록"}` 로. 겹치는(간섭) 바디는 거절, 조립의 마지막에 둔다) ·
  `divide_face`(target, on — 나눌 면 질의, shape circle|rect|sketch, radius · size · at ·
  sketch, tag — **면을 영역으로 나눈다**: 형상은 그대로이고, 생긴 조각에 tag 가 붙어 조건의
  선택 그룹이 `{"what":"faces","tag":"<tag>"}` 로 집는다. `shape: sketch` 는 앞의 스케치 윤곽대로
  — 도형 여럿이면 패치도 여럿, 구멍 뚫린 도형이면 고리. 스케치는 나눌 면 위에(평면을 그 면에)
  그리고, `on` 을 비우면 스케치가 놓인 면을 저절로 고른다. 치수를 바꿔도 같은 자리에 다시 생긴다)
  - `edges` 는 `all` · `vertical` · `horizontal` · `top` · `bottom`, `{"near": [[x,y,z]…]}`
    (엣지 중점 위치 — 사람이 3D 에서 누른 것), 또는 **`{"query": {…}}`**(`recipe_find` 의 질의).
    **AI 는 query 를 쓴다** — 위치는 DOE 가 치수를 바꾸면 그 자리에 엣지가 없어 실패한다.
    예: 구멍 위 원 `{"query":{"kind":"circle","radius":5,"near":[35,0,100]}}`, 블록 윗면 둘레
    `{"query":{"of_face":{"body":"블록","normal":[0,0,1]}}}`(of_face = 그 면들의 테두리).
    면 칸(shell.open · draft.faces · defeature.faces · chamfer.reference)도 같은 `{"query": …}`
    를 받는다. near 가 없으면 맞는 것 전부, 있으면 가장 가까운 하나
- 배치 `pattern`(source, kind linear|grid|circular, count, spacing | count_y+spacing_y | axis+angle)
  — 결과는 **복사본 묶음**
  이라 `cut` 의 tools 나 `union` 의 targets 로 쓴다 · `transform`(target, translate, rotate,
  scale, pivot — 회전 · 배율의 중심) · `mirror`(target, plane, keep_original)
- **기준축 · 기준면** — 형상을 만들지 않고 축 · 평면 칸이 가리킨다. 원점을 지나는 `X` · `Y` · `Z`
  축과 `XY` · `YZ` … 평면 말고 아무 축 · 평면에 돌리고 비추고 그릴 때.
  - `datum_axis` — `origin`+`direction` · `through` [[두 점]] · `target`+`select`(앞 입체의 원통 ·
    원뿔면의 축 또는 직선 엣지, `recipe_find` 의 질의 — 예 `{"what":"faces","kind":"cylinder",
    "near":[x,y,z]}`) 중 하나. `revolve.axis` · 원형 `pattern.axis` · `datum_plane.hinge` 에
    id 로 쓴다.
  - `datum_plane` — `plane`({name, origin} 또는 {origin, normal}) · `points` [[세 점]] ·
    `target`+`select`(앞 입체의 평면 하나) 중 하나, 그리고 `offset`(법선 쪽으로 띄우기) ·
    `hinge`+`angle`(축 둘레로 기울이기). 평면 칸(스케치 · split · section · draft.neutral · hole)에
    `{"datum": "<id>"}` 로, `mirror.plane` 에 id 로 쓴다.
  - 형상의 평면에서 뽑은 기준면의 원점은 **전역 원점을 그 면에 내린 점**, X 는 전역 X 방향 —
    그래서 누운 면(윗면)에 그린 스케치의 좌표는 **전역 x · y 그대로** 준다(높이만 면을 따른다).
  - 형상에서 뽑은 기준은 **치수를 바꿔도 따라간다** — 「구멍 축 둘레로 핀 여섯」 ·
    「윗면에서 10 띄운 면에 스케치」 가 DOE 설계점마다 맞는다. select 가 여럿에 맞으면 거절된다
    (near 로 하나를 고른다).
  - 예 — 구멍 축 둘레로 6 개: `{"op":"datum_axis","id":"구멍축","target":"판",
    "select":{"what":"faces","kind":"cylinder","radius":10}}` →
    `{"op":"pattern","source":"핀","kind":"circular","count":6,"axis":"구멍축"}`

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

**실험계획(DOE)** — 대상 하나(부품 · 지그 · 조립)의 변수를 훑어 인스턴스를 여럿 만들 때
(`doe_create(work_id=…)` 로 대상을 잇는다):
1. 레시피에 `params` 로 바꿀 치수를 둔다. **연결부를 이루는 칸이 그 치수를 쓰지 않으면 안 변한다.**
2. `doe_preview` 로 **개수를 먼저 센다** — 격자는 곱으로 늘어난다(인자 넷에 5단계면 625개,
   한 번에 만드는 상한은 관리자가 서버 설정 화면에서 정한다, 기본 200 — `doe_preview` 의
   `max`). 값은 인자의 `resolution`(가공 단위, 기본 0.1 mm)으로 맞춰진다.
3. `doe_create` — 점마다 형상을 만들어 **서버 보관 폴더**에 `points/p0001.step` 과
   `manifest.csv`(번호 · 바꾼 변수 값 · 파일 · 상태)를 쓴다. 질량 · 크기는 계산하지 않는다 —
   결과는 해석이 낸다. 다 만들어지면 `doe_export` 로 **공유 폴더**에 보낸다 — 해석(ANSYS)은
   그때부터 그 폴더를 읽는다(만드는 중에 보내지 않는다).
4. **결과는 이 플랫폼에 돌아오지 않는다.** 해석 플랫폼이 폴더를 읽어 풀고, 결과를 보고
   설계점을 고르는 일도 거기서 한다 — 여기서 「어느 점이 좋은가」 를 묻지 마라. 점마다
   `points/pNNNN.topology.json` 에 **영역 지문과 그 점의 변수 값**이 함께 있어, 해석 쪽이
   파일만 보고 「이 결과가 두께 8 짜리」 를 안다.
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

**작업은 셋 중 하나다**(`create_work(kind=…)`):
- `part` · `jig` — **그리는 것**. 레시피 하나이고 방법이 같다. 둘은 **서로 아무 관계가 없다**.
- `assembly` — **놓는 것**. 부품 · 지그를 가져다 서로 위치시킨다:
  `{"op":"component","source":"part:<id>|jig:<id>|work:<id>","params":{"두께":"=부품_두께"},
  "translate":[0,0,"=지그_높이"],"rotate":[0,0,0]}` 여럿 + 마지막에
  `{"op":"group","targets":[…]}`(붙이지 않고 묶는다 — 부품과 지그는 따로 남아야 한다).
  가져오는 것은 STEP 이 아니라 **살아 있는 레시피**라, `params` 로 구성품의 치수를 조립의
  변수로 움직일 수 있다 → 조립을 그대로 실험계획으로 훑는다.
  **부품 + 지그를 놓는 조립은 `assemble_jig_on_part(part_source, jig_work_id)` 로 만든다** —
  생성된 지그의 좌표계(부품 XY 중심이 원점 · 판 윗면 z=0 · 부품은 받침 높이만큼 뜸)를 서버가
  맞춘다. 손으로 좌표를 계산해 `translate` 를 적지 않는다. 손으로 그린 지그는 어림(`guessed`)
  이니 사용자에게 자리를 확인받는다. 조립을 저장하기 전에 `recipe_interference` 로 구성품끼리
  겹치지 않는지 본다 — 서버는 겹친 채로도 저장한다.

**지그 작업은 두 길로 시작한다** — 어느 쪽이든 결과는 `kind="jig"` 작업이고 그 뒤는 같다:
- **부품에서 생성**: `run_jig(source, options)` — 부품(`work:<id>` · `part:<id>`)의 형상에서
  규칙으로 배치해 **새 지그 작업**을 만들고, 결과 STEP 이 그 첫 버전이 된다. 형식은
  `options.kind`: `clamped`(판 · 받침 · 핀 · 클램프) · `bolted`(관통 구멍으로 볼트 — 진동 · 충격
  시험) · `bending`(3점 굽힘 롤러 + 노즈) · `drop`(낙하 자세 + 바닥 + 낙하물). 먼저 `jig_preview`
  로 본다. 출발점일 뿐이다 — 받침을 옮기거나 튜닝부를 붙이는 일은 그 다음에 `save_version`
  으로 그린다(그때부터 `params` 로 변수를 심는다).
- **빈 화면에서 그린다**: 생성기가 만들 수 없는 지그(공진을 맞추는 시험 지그, 특수 치구)는
  `create_work(kind="jig")` 로 시작해 레시피로 그린다.
다 그리면 `promote_jig_recipe` 로 지그 카탈로그에 올린다(작업에 이어 둔 부품이 자동으로 따라간다).

제품을 기준으로 **지그**를 그릴 때:
1. `list_parts` → `part_geometry(part_id)` — 크기 · 바닥 평면 · **구멍(지름 · 중심 · 깊이)** 을
   읽는다. 내 작업이라면 `work_geometry(work_id)`.
2. 자동으로 뽑으려면 `run_jig("part:<part_id>")` (옵션은 `jig_options`) — 복사할 필요가 없다.
3. 손으로 그리려면 받은 `step_artifact_id` 로 제품을 불러와 쓴다:
   `{"op":"import_step","file":"<step_artifact_id>","id":"제품"}` →
   `{"op":"offset","target":"제품","amount":0.3,"id":"여유"}` →
   블록에서 `cut` 하면 **제품이 앉는 포켓**이 된다. 제품 구멍 자리에는 `cylinder`(align z=min)로
   핀을 세운다.
4. 그린 뒤 `recipe_geometry` 로 **확인한다** — 포켓 깊이 · 핀 지름이 뜻대로인지.

말로 받은 치수를 옮길 때:
- 호는 `radius` · `tangent`, 장공은 `slot.measure: "centers"`, 삼각형은 변 · 각 — **도면이 주는
  값을 그대로** 넣어라. 좌표로 환산하면서 틀리는 일이 제일 많다.
- 접어 만드는 것은 `sheet_metal`(옆모습 꺾은선이 주어질 때) 또는 `bend`(**전개도** — 펼친 판의
  치수 · 구멍 자리가 주어질 때, 원통에 감는 띠), 살을 붙이는 리브는 `path`(두께 있는 선), 감싸는 판은
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
5. 지그가 필요하면 `run_jig("work:<work_id>", options)` — 새 지그 작업이 생긴다. 간섭이 있으면
   결과의 `plan.notes` 와 `interference.items` 를 읽고 (a) 옵션(판 여유 · 받침 수 · 클램프 수)
   또는 (b) 부품을 고쳐 다시(지난 지그 작업은 `delete_work`).
6. 사용자가 시키면 `promote_part` / `promote_jig_recipe`.

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

## conditions

해석 조건(구속 · 하중 · 접촉 · 초기조건 · 메시 힌트 · 해석 설정 · 물성)은 `set_conditions` 로 작업
버전에 붙인다. **먼저 `conditions_schema` 를 읽는다** — 종류마다 칸 · 설명 · 단위 · 받는 대상이
거기 있다.

1. **값은 늘 mm · N · MPa · tonne 으로 적는다**(`input_system`). `units.system` 은 **내보내기**
   단위계다 — SI 를 골라도 적는 값은 mm · MPa 다(점 파일을 만들 때만 옮긴다).
2. **조건은 선택 그룹만 가리킨다.** `named_selections` 에 `{name, entity, select}` 를 두고 조건의
   `on`(접촉은 `source` · `target`)에 그 이름을 적는다. 셀렉터는 `recipe_selectors`(찍은 점 →
   후보) 또는 `recipe_find`(질의 → 면 목록)로 얻는다 — **`recipe_find` 로 그 셀렉터가 몇 개를
   집는지 먼저 본다.** 그룹은 `near` 가 없으면 맞는 것 **전부**, `near` 가 있으면 가장 가까운
   하나(`limit` 을 주면 그만큼)다.
   - 규칙의 숫자 칸에도 도면 변수 식을 쓴다 — `{"kind": "cylinder", "radius": "=지름 / 2"}` 는
     DOE 가 구멍 지름을 훑어도 그 구멍을 잡는다. `near` 를 식으로 적으면 그 식대로 옮겨 가고(자동
     따라가기는 하지 않는다), 숫자로 적으면 치수를 따라 저절로 옮긴다.
   - 점 그룹(`entity: vertex`)의 지문은 자리 `{"point": [x, y, z]}` 하나다. 점 그룹에 붙인
     좌표계는 원점만 그 점, 방향은 전역.
   - **조립(바디 여럿)은 `body` 로 고른다** — `{"what": "faces", "body": "블록", "normal":
     [0, 0, -1]}` 은 블록의 아랫면 하나다. 「+Z 평면」 만 쓰면 판 윗면과 블록 윗면을 함께 집는다.
     좌표(`near`)가 없어 치수를 훑어도 헛집지 않는다.
3. **종류마다 받는 대상이 정해져 있다** — 사양표의 `groups.<묶음>.accepts[종류]`:
   - 접촉 · 압력 · 마찰 없는 · 압축 전용 · 탄성 지지: **면**
   - 원통 지지 · 베어링 하중: **원통면** — 선택 규칙에 `"kind": "cylinder"` 가 있어야 한다
     (`recipe_find({"what": "faces", "kind": "cylinder", "radius": r})` 로 찾고 그 셀렉터를 그대로
     쓴다). `near` 만 있는 규칙은 치수가 바뀐 설계점에서 다른 모양의 면을 집을 수 있어 거절된다.
   - 볼트 예압: 원통면 또는 바디
   - 힘 · 고정 지지 · 변위: 면 · 엣지 · 점 / 모멘트 · 원격 변위: 면 · 엣지
   - 메시 힌트: 면 · 엣지 · 바디(또는 「전체」)
   - 초기 온도 · 초기 속도: 바디 / 중력 · 가속도 · 회전 속도: 대상 없음
   어기면 저장이 거절되고 메시지가 **무엇을 어떻게 고칠지** 말한다 — 그대로 고쳐 다시 부른다.
4. **종류에 필요한 칸만** 쓴다 — 칸의 `only_for` 에 종류가 있어야 뜻이 있다(`when` 은 다른 칸의
   값에 따른 것). 해석 설정도 종류마다 다르다: 모달은 `modes`, 명시적은 `end_time`, 조화 응답은
   `frequency_range` 등. 빠진 필수 값은 저장에서 거절된다. 비운 칸은 기본값이다.
5. 숫자 칸에는 레시피와 같은 식(`"=압력"`)을 쓸 수 있다 — 변수는 레시피 `params`(mm). 실험계획이
   그 변수를 훑으면 형상과 조건이 함께 움직인다.
6. **물성**: `material_search` 로 찾고 `material_get` 으로 받아 그 `condition_item` 을
   `materials` 에 넣는다 — 값을 지어내지 않는다. `apply_to` 는 바디 이름 목록(`recipe_bodies`,
   단품이면 `["전체"]`). 바디 하나에 물성 하나.
7. 지금 저장된 조건은 `get_work` · `get_version` 의 `current.conditions` 에 있다 — 사람이 만든
   조건이 있으면 **읽고 고쳐서** `set_conditions` 로 보낸다(통째로 덮어 지우지 않는다).

### 조건을 실어 DOE 로 — 끝에서 끝까지

1. 도면: `create_work` / `patch_work` — 훑을 치수는 `params` 의 변수로.
2. 조건: `set_conditions`(선택 그룹 · 구속 · 하중 · 접촉 · 해석 설정 · 물성).
3. DOE: `doe_run(work_id=…, recipe=그 버전의 레시피, factors=…, idempotency_key=…)` —
   **`conditions` 를 안 주면 그 작업의 현재 조건이 실린다.** 점 파일마다 그 점의 치수로 풀린
   조건 · 영역이 들어간다.
4. **재료도 훑을 수 있다**: 후보 재료를 조건의 `materials` 에 `apply_to: []` 로 담아 두고
   인자에 `{"name": "블록 재료", "mode": "material", "bodies": ["블록"], "values": [이름 · 번호…]}`.
   치수 인자와 섞어 격자 · LHS 로 조합한다. 형상은 그대로라 한 벌을 나눠 쓴다.
5. **조건 값도 훑는다** — 무엇을 어떻게:
   - 숫자 칸(하중 크기 · 변위량 · 마찰계수 · 온도 · 끝 시간 · 모드 수 …): 도면 `params` 에 변수를
     두고(형상에 안 써도 된다) 조건 칸에 `"=압력"` 처럼 적은 뒤 그 변수를 인자로 훑는다. 정수 칸
     (모드 수 · 단계 수)도 식을 받는다 — 풀려서 정수여야 한다.
   - 고르는 칸(구속 · 하중 · 접촉의 종류, 정식화, 선택 그룹, 해석 종류, 켬끔, 변위의 자유 `null` ↔
     고정 `0`): `{"mode": "choice", "target": {"group", "item"(이름 또는 1 부터 번호), "field"},
     "values": [...]}`. 바꿔 볼 값에 필요한 칸(마찰이면 `friction`)은 조건에 미리 적어 둔다 —
     만들기 전에 값마다 검사해 없으면 거절한다.
   - 물성 배율(민감도): `{"mode": "scale", "bodies": [...], "property": "탄성계수"(또는 표준 열쇠 ·
     밀도 · 푸아송비), "values": [0.9, 1, 1.1]}` — 원본은 그대로, 점 파일의 `converted` 값에만
     곱하고 `converted.scaled` 에 적는다.

