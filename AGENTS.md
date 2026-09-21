# 개발 지침

이 저장소에서 코드를 고칠 때 지키는 규칙. **이 파일이 정본이다.** `CLAUDE.md` 는 이 파일을
가리키기만 한다.

## 이 저장소가 무엇인가

**CompCore(Component Engineering Core) — 부품 하나를 그려 지그(fixture)를 만들고,
변수를 훑어(DOE) 해석으로 넘기는 독립 플랫폼.**

[StandardPlatform](../StandardPlatform) 에서 로그인 · 설정 · 오류 규약 · 배포 형태 같은
**제반 구조만 가져왔다.** StandardPlatform 의 인스턴스(확장 모듈 · 온톨로지 · 부서)가 아니다 —
그쪽의 `EXTENSIONS` 나 `app/extensions` 같은 기제는 여기 없고, 앞으로도 넣지 않는다.
지그 생성은 이 저장소의 **코어**(`backend/app/core`)가 한다.

    제품 STEP ─▶ Geometry Understanding ─▶ Feature Recognition ─▶ Fixture Planning
             ─▶ Support · Locator · Clamp ─▶ Jig 자동 생성 ─▶ 간섭 검사 ─▶ STEP

## 층

    backend/app/core       build123d 위의 순수 파이썬. 웹 · DB 를 모른다.
    backend/app/modules    API. core 를 부르고 결과를 DB · filestore 에 남긴다.
    backend/app/shared     인증 · 오류 · 로그 · 파일 저장소 — 모듈이 함께 쓰는 것.
    frontend/src/modules   화면. 모듈 이름은 백엔드와 같다.

- **`core` 는 `fastapi` · `sqlalchemy` · `app.modules` · `app.shared` · `app.config` 를 import
  하지 않는다.** 그래야 `scripts/generate_jig.py` 와 단위 시험이 서버 없이 코어만 돌린다 —
  기하 알고리즘을 고칠 때마다 DB 를 띄우면 아무도 안 고친다. `tests/architecture` 가 검사한다.
- 단계 사이의 자료는 `core/model.py` 의 데이터클래스다. 한 단계를 다른 알고리즘으로 갈아
  끼워도 나머지는 그대로여야 한다.
- **코어의 좌표계는 둘이다.** 계획(planning)까지는 *제품 좌표계*(제품 바닥 z=0, XY 중심 원점),
  부품(elements)부터는 *최종 좌표계*(판 윗면 z=0, 제품은 `product_lift` 만큼 위). 옮기는
  자리는 `assembly.py` 하나다.
- 요약(`JigResult.summary()`)은 JSON 이어야 한다 — DB(JSONB)와 화면이 읽는다. 기하 객체를
  넣지 않는다.

## build123d 에서 실측으로 겪은 것

- **`Compound(children=[…])` 는 자식을 옮긴다.** 원본 Compound 가 비고, 옮겨진 형상을 따로
  내보내면 빈 파일이 나온다(product.glb 가 240 바이트). 한 벌로 묶을 때는 `copy.copy` 한다
  (`core/export.combined`).
- `a & b` 는 닿기만 하면 부피 0 인 Compound 를 돌려준다. `a.intersect(b)` 는 `None` 이나
  `ShapeList` 를 돌려주므로 `&` 를 쓴다(`core/interference.py`).
- `Face.is_inside(point)` 는 구멍을 안다 — 구멍 중심에서 False. 그러나 받침 **원판**이 구멍에
  걸리는 것은 못 잡으므로 구멍과의 거리를 따로 본다(`planning._clear_of_holes`).
- 구멍과 보스는 원기둥면의 **바깥 법선이 축을 향하는가**로 가른다(`features._is_hole`).
- OCP 는 mypy 에 타입이 없다. `pyproject.toml` 이 `app.core.*` 만 느슨하게 본다 — 그 경계
  밖(`modules`)은 strict 그대로다.

## 내 공간과 승격

- **내 작업(Work)이 곧 공간이다.** 작업 · 그 버전 · 그 작업이 건 job · 작업물은 소유자와 관리자만
  본다(`works.require_owner` · `jobs.require_visible`). 목록도 내 것만 나온다.
- 남에게 내놓는 유일한 길은 **승격**(`works.promote_part` · `promote_jig`)이다. 카탈로그 버전은
  레시피 · 요약을 **복사**해 들고, 작업물은 job 을 그대로 가리킨다 — 그래서 승격된 job 의 작업물은
  누구나 받는다. 작업이 지워져도 카탈로그는 남는다.
- 카탈로그 버전은 고치지 않는다. 고치려면 「내 공간으로 복사」(`parts.copy_to_work`) → 고침 →
  다시 승격(v2).
- 지그 승격은 **어느 부품 버전의 지그인가**를 고정한다. 제품(그때의 형상 버전)이 부품에 없으면
  함께 올린다(`promote_product`). 지그의 제품이 현재 버전이 아니면 거절한다 — 옛 버전을 올리려면
  되돌린 뒤.
- 올린 STEP 은 작업물(`kind="import_step"`) + `import_step` 노드 하나짜리 버전이다. 제품 경로 ·
  도형 스펙 같은 다른 길은 없다 — 제품은 늘 「이 작업의 형상」 하나다.

## CAD 레시피

- **모델은 레시피(연산 트리 JSON)다** — `core/recipe/schema.py` 가 노드 종류 · 칸의 정본이고,
  `describe()` 가 그것을 JSON Schema 로 내보내 편집기와 AI 프롬프트가 읽는다. 연산을 더하면
  `schema.py` 에 노드 클래스, `evaluate.py` 에 가지 하나 — 화면은 안 고친다.
- **버전은 고치지 않는다.** 새 버전을 만든다. 되돌리기도 옛 레시피로 새 버전이다. 그래야 이력이
  한 줄로 남고 AI 의 제안이 「후보 버전」 으로 들어갈 자리가 있다.
- 평가는 두 길: 미리보기(요청 안, 동기 — 편집기가 칸을 고칠 때마다)와 버전 평가(`Job(kind="cad")`,
  STEP · glTF 작업물). 같은 `core.recipe.evaluate` 를 지난다.
- 검증 메시지는 **어느 노드 · 어느 칸이 왜** 인지 말한다(`RecipeValidationError.problems`,
  `RecipeError(node_id, message)`). 그것이 AI 에게 돌려주는 말이고 편집기가 빨간 줄을 긋는 근거다.
  OCC 의 말("BRep_API: command not done")은 사람에게 뜻이 없으니 노드 종류에 맞게 바꾼다.
- **불리언 뒤에는 `clean()`.** 면이 정확히 포개진 두 덩어리(거울 · 대칭 회전체)를 합치면 OCC 가
  부피가 음수인 솔리드를 내놓는다(실측). 평가기가 결과마다 `is_valid` 와 부피를 본다.
- `import_step` 노드의 `file` 은 작업물 id 다. 코어는 경로를 모르고 `resolve_file` 콜백으로 받는다.
- **편집기의 노드 목록은 `frontend/src/modules/cad/recipeSpec.ts` 다.** 서버에 연산을 더하면 거기
  한 항목을 더한다 — `recipeSpec.test.ts` 가 서버 `schema.py` 의 op 리터럴과 대조한다.
- 3D 에서 고른 엣지는 **위치(중점)**로 적는다(`EdgeNear`). 인덱스는 형상을 조금만 고쳐도 바뀐다.
  면을 고르면 그 면의 중심 · 법선이 `PlaneSpec.origin/normal` 이 된다. 미리보기는 `/cad/recipe/mesh`
  (면 · 엣지 단위)이고 결과 화면은 glTF — 편집기만 고르기가 필요하다.

## 이름과 식별자

- 설치 이름은 `.env` 가 덮을 수 있다(`APP_NAME` · `APP_SLUG`). 코드는 `get_settings().app_name`
  으로 읽고 `branding.py` 에서 import 하지 않는다 — `config.py` 만 예외.
- `APP_SLUG` 에서 DB 이름과 refresh 쿠키 이름이 나온다. 같은 서버의 다른 플랫폼과 겹치면
  **번갈아 로그아웃**되고 그 원인은 코드 어디에도 없다. 기본값 `compcore`.
- **포트는 8060 (개발 8061 · Vite 5230).** 플랫폼마다 10씩 벌린다. 정본 표는
  `StandardPlatform/docs/새-플랫폼-만들기.md` 3.6 이고 이 플랫폼도 거기 적혀 있다 — 8050 은
  그 표에서 PartTrace 예약 자리라 비켜 갔다.
- 오류 코드는 `errors.code("MODULE", n)` 로만 만든다(`CCR-JIGS-0003`). 손으로 이으면
  시험이 잡는다.

## 구조

- 모듈 이름은 백엔드와 프론트가 같다. `app/modules/<name>` <-> `frontend/src/modules/<name>`.
  예외는 `tests/architecture/test_boundaries.py` 의 `FRONTEND_MERGED` 에 **사유와 함께**.
- 모듈끼리 라우터를 직접 부르지 않는다. 조립 지점은 `app/main.py` 하나다.
- `shared` 는 도메인 라우터를 모른다.
- 새 ORM 모델은 `app/all_models.py` 에 적는다. 빠뜨리면 autogenerate 가 **기존 표를 지우는**
  마이그레이션을 만든다.
- 지우지 않는다. 계정 · 프로젝트는 `deleted_at` 만 채운다. 결과 파일도 남긴다.
- 행은 마이그레이션에 넣지 않는다. 첫 관리자는 `scripts/seed_install.py` 가 심는다.

## API

- 성공 응답은 리소스 그대로, 오류만 봉투(`{"error": {code, message, request_id, details}}`).
- 오류 본문을 라우트에서 직접 만들지 않는다 — `AppError` 계열을 raise 한다.
- 부분 수정은 `model_dump(exclude_unset=True)` 로 "안 보낸 것" 과 "비운 것" 을 구별한다.
- 목록은 서버가 상한을 강제한다(`shared/pagination.py`).
- 폴링 경로를 만들면 `shared/access_log.py` 의 `_SKIP` 에 더한다.
- 스키마를 바꿨으면 `python scripts/export_openapi.py` 와 `npm run api:types` 를 함께 돌린다.
- **만드는 일은 전부 작업(Job)이다.** 지그 생성은 `POST /works/{id}/jig-runs` 가 `Job(kind="jig")`
  을 걸고 202 로 돌아온다. 워커(`python -m app.worker`)가 DB 큐에서 집어 돌리고, 화면은 `GET /api/jobs/{id}`
  를 폴링한다([ADR 0003](docs/adr/0003-DB-를-큐로-쓴다.md)).
  - 새 종류는 `app/handlers.py` 에서 등록한다 — 서버와 워커가 같은 함수를 부른다. 실행 함수는
    `(input, options, out_dir, progress) → Outcome` 이고 **웹 · DB 를 모른다.**
  - 사람이 읽고 고칠 수 있는 실패는 `registry.UserFacingError` 로 던진다 — 메시지가 그대로 화면에
    간다. 다른 예외는 코어의 버그로 보고 트레이스백을 남긴다.
  - 작업의 `input` 은 **스냅숏**이다(지그면 그때의 형상 레시피). 작업(work)의 형상이 나중에 바뀌어도
    그 job 이 무엇으로 돌았는지 남아야 한다.
  - `JOBS_INLINE=1` 이면 워커 없이 요청 안에서 돈다. 시험이 그 길을 쓴다. 워커 경로 자체는
    `tests/api/test_jobs.py` 가 `claim_next → execute` 를 직접 부른다.
- 결과 파일은 `artifacts` 행이고 `GET /api/artifacts/{id}/download` 로 받는다. 토큰이 있어야 한다.
  화면은 `fetchBlob` 으로 받아 Blob URL 을 뷰어에 준다 — `<a href>` 나 `<img src>` 에는 access
  토큰이 실리지 않는다.

## 프론트

- 스타일은 Tailwind 유틸리티. 전역 CSS 클래스를 새로 만들지 않는다.
- API 절대주소를 코드에 넣지 않는다. 항상 상대경로 `/api`.
- 사이드바(`shared/layout/navigation.ts`)가 화면 목록의 정본이다. `router.test.tsx` 가 검사한다.
- 역할 판정은 `shared/auth/roles.ts` 한 곳. 표시일 뿐 권한이 아니다 — 권한은 서버가 판정한다.
- 상태의 말과 색은 `StatusBadge` 가 정한다.
- **3D 는 `shared/viewer/ModelViewer` 가 그리고, 쓰는 화면에서 `lazy()` 로 받는다.** three 한
  덩어리가 600KB 다 — 지그를 안 보는 화면까지 매번 받을 이유가 없다. 색은
  `shared/viewer/colors.ts` 가 정한다(제품 파랑 · 지그 회색) — 뷰어와 범례가 같은 값을 쓴다.
- 빈 목록은 이유를 말한다(`EmptyState`). 되돌릴 수 없는 일은 무엇이 사라지는지 적는다
  (`ConfirmDialog`). 본문은 오류 경계 안에 있다(`ErrorBoundary`).

## 개발 서버와 워커

`run.py` 는 개발에서 워커를 **watchfiles 로** 띄운다 — `app/` 이 바뀌면 워커가 다시 뜬다. uvicorn 의
reload 는 API 만 새로 띄우기 때문에, 워커를 그냥 자식으로 두면 모델을 바꾼 뒤 옛 워커가 매 루프
SELECT 에서 죽어 「작업이 queued 에서 안 움직인다」 가 된다(실측, 2026-09-18). **마이그레이션을
돌렸으면 서버를 다시 띄운다** — 그 전에 뜬 워커는 watchfiles 가 없는 옛 run.py 일 수 있다.

## 다른 사람의 프로세스

**`pkill -f` 로 서버를 내리지 않는다.** 개발 PC 에는 사용자가 직접 띄운 `run.py` 가 떠 있을 수
있고, 이름으로 죽이면 그것이 죽는다(실측 — 2026-09-18 에 그렇게 사용자의 서버를 내렸다). 자기가
띄운 것은 PID 를 들고 있다가 그것만 내린다. 포트가 잡혀 있으면 「누가 쓰나」 를 먼저 본다:
`ss -ltnp 'sport = :8061'`.

## MCP 서버

- `mcp_server/` 는 **한 파일 `server.py`**, 그 폴더의 `venv`, streamable-http(백엔드 포트 +2).
  백엔드 venv 에 `mcp` 를 깔지 않는다 — 시험의 HTTP 스택이 바뀐다(StandardPlatform 실측).
  진짜 앱에 붙여 보는 시험은 `backend/tests/api/test_mcp_tools.py` 가 가짜 `mcp` 로 도구 함수만
  꺼내 ASGI 로 돌린다.
- MCP 에 규칙을 두지 않는다. 사용자의 PAT 를 백엔드에 그대로 넘기고 검증 · 권한은 백엔드가 한다.
- **도구는 늘 dict 하나를 돌려준다.** FastMCP 는 리스트를 항목마다 다른 content 로 쪼개 클라이언트가
  첫 항목만 읽는다(실측). 큰 것(삼각형 · 진행 로그)은 빼고 요약만.
- 가이드(`guide/GUIDE.md`)를 서버가 쥔다. 노드 종류를 더하면 가이드의 `recipe` 절도 고친다.

## 검증

고치고 나서 이것을 돌린다. **마이그레이션을 만들었으면 그 자리에서 개발 DB 에 올린다**
(`alembic upgrade head`).

```bash
cd backend
.venv/bin/ruff format . ../mcp_server --config pyproject.toml
.venv/bin/ruff check . ../mcp_server --config pyproject.toml
.venv/bin/mypy
.venv/bin/python -m pytest
.venv/bin/python -m alembic check
cd ../frontend && npm run build && npm test && npm run lint
mcp_server/venv/bin/python -m pytest mcp_server/tests      # 저장소 루트에서
```

테스트는 개발 `.env` 의 접속 정보에서 `<이름>_test` 를 파생해 쓴다. **개발 DB 를 건드리는
테스트는 쓰지 않는다.** 시험은 파일을 임시 폴더에 쓴다(`tests/conftest.py` 의 `FILESTORE_DIR`).

코어만 빨리 돌려 보려면:

```bash
cd backend && .venv/bin/python scripts/generate_jig.py            # 시연 제품
.venv/bin/python scripts/generate_jig.py part.step -o out/           # 제품 STEP
.venv/bin/python scripts/generate_jig.py --spec '{"kind":"box","length":60,"width":40,"height":20}'
```

## 문서

- 판단이 갈렸던 결정은 `docs/adr/NNNN-제목.md` 에 남긴다 — 결정 · 배경 · 대안 · 결과.
- 실측으로 드러난 함정은 근거와 함께 적는다. "이렇게 하세요" 보다 "이렇게 안 하면 이런 일이
  났다" 가 다음 사람에게 유용하다.
