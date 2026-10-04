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
- **`Face.wrap` 은 근사다** — 일반 곡면에 맞춰 엣지를 조금씩 늘려 스플라인으로 맞춘다. 원통에
  감을 때는 그것을 쓰지 않고 엣지를 원통의 매개변수 평면(각 · 높이)으로 옮긴다(`recipe/bend.py`).
- **build123d 의 `.volume` 은 오차가 크다** — B-스플라인 면이 있으면 4574 mm³ 를 4571 로 낸다
  (실측). 정확도를 시험할 때는 `BRepGProp.VolumeProperties_s(shape, props, 1e-9, False)`.
- **`Vector.get_angle` 은 도를 돌려준다** — 라디안인 줄 알고 `degrees` 를 또 씌우면 90° 가
  5157° 가 된다.
- **`Plane.rotated` 는 법선까지 돌린다** — 부재 축 둘레로 단면만 돌리려다 부재 방향이 바뀌었다.
  축 둘레 회전은 x · y 방향을 직접 돌린다(`recipe/frame.py`).
- **`Rectangle` 은 가운데 맞춤, `Polygon` 은 준 좌표 그대로**(align 기본값이 다르다).
- **OCC 의 면 삭제(`BRepAlgoAPI_Defeaturing`)는 실패를 말하지 않을 때가 있다** — 모든
  모서리를 둥글린 ㄴ자의 필렛을 한꺼번에 지우면 **경계상자로 메운** 상자를 돌려준다(6424 →
  24000 mm³). 결과의 부피 변화가 지운 면들의 경계상자 안에 드는지 본다(`recipe/defeature.py`).
- **`make_brake_formed` 는 꺾은선을 그대로 둥글린다** — 두께가 굽힘 안쪽으로 붙으면(꺾은선이 바깥
  면) 안쪽 반지름이 r - t 가 되어 r = t 에서 실패하고, r < t 면 두께가 틀린 판이 나왔다. 두께가 어느
  쪽으로 붙는지는 평면 · 도는 방향에 따라 바뀌므로 띄워 보고 재서 굽힘마다 r 또는 r + t 로 돌린다
  (`recipe/evaluate._bend_radii`).
- **`BoundBox.add` 는 새 상자를 돌려준다** — 제자리에서 키우지 않는다. `box.add(…)` 만 쓰면
  첫 상자 그대로라, 볼트 넷의 와셔 자리 중 하나만 잡혔다(`recipe/imprint.py`).
- OCP 는 mypy 에 타입이 없다. `pyproject.toml` 이 `app.core.*` 만 느슨하게 본다 — 그 경계
  밖(`modules`)은 strict 그대로다.

## 내 작업 공간과 등록

- **내 작업(Work)이 곧 공간이다.** 작업 · 그 버전 · 그 작업이 건 job · 작업물은 소유자와 관리자만
  본다(`works.require_owner` · `jobs.require_visible`). 목록도 내 것만 나온다.
- 남에게 공개하는 유일한 길은 **등록**(`works.promote_part` · `promote_jig_recipe`)이다. 카탈로그
  버전은 레시피 · 해석 조건 · 요약을 **복사**해 들고, 작업물은 job 을 그대로 가리킨다 — 그래서 등록된
  job 의 작업물은 누구나 받는다. 작업이 지워져도 카탈로그는 남는다. 남이 이어서 고치는 길은
  **복사**뿐이다(`POST /parts/{id}/copy-to-work` · `POST /jigs/{id}/copy-to-work` · DOE 는
  `POST /doe/{id}/clone`) — 원본은 건드리지 않고 내 것을 새로 만든다.
- 카탈로그 버전은 고치지 않는다. 고치려면 「내 작업 공간으로 복사」(`parts.copy_to_work`) → 고침 →
  다시 등록(v2).
- **예외 하나 — 규격 부품 가져오기**(`parts.import_standard`, 시스템 관리자만). 다른 서버에서 내보낸
  묶음의 레시피로 카탈로그 버전을 **작업 없이** 바로 만든다(품번으로 짝짓는다, ADR 0005). 들어오는
  레시피는 STEP · 다른 도면을 가리킬 수 없다 — 규격 사양의 형상 기준이 거절한다.
- 지그 등록은 **어느 부품 버전의 지그인가**를 고정한다. 제품(그때의 형상 버전)이 부품에 없으면
  함께 등록한다(`promote_product`). 지그의 제품이 현재 버전이 아니면 거절한다 — 옛 버전을 등록하려면
  복원한 뒤.
- 업로드한 STEP 은 작업물(`kind="import_step"`) + `import_step` 노드 하나짜리 버전이다. 제품 경로 ·
  도형 스펙 같은 다른 길은 없다 — 제품은 늘 「이 작업의 형상」 하나다.

## CAD 레시피

- **모델은 레시피(연산 트리 JSON)다** — `core/recipe/schema.py` 가 노드 종류 · 칸의 정본이고,
  `describe()` 가 그것을 JSON Schema 로 내보내 편집기와 AI 프롬프트가 읽는다. 연산을 더하면
  `schema.py` 에 노드 클래스, `evaluate.py` 에 가지 하나 — 화면은 안 고친다.
- **버전은 고치지 않는다.** 새 버전을 만든다. 복원도 옛 레시피로 새 버전이다. 그래야 이력이
  한 줄로 남고 AI 의 제안이 「후보 버전」 으로 들어갈 자리가 있다.
- 평가는 두 길: 미리보기(요청 안, 동기 — 편집기가 칸을 고칠 때마다)와 버전 평가(`Job(kind="cad")`,
  STEP · glTF 작업물). 같은 `core.recipe.evaluate` 를 지난다.
- 검증 메시지는 **어느 노드 · 어느 칸이 왜** 인지 말한다(`RecipeValidationError.problems`,
  `RecipeError(node_id, message)`). 그것이 AI 에게 돌려주는 말이고 편집기가 빨간 줄을 긋는 근거다.
  OCC 의 말("BRep_API: command not done")은 사람에게 뜻이 없으니 노드 종류에 맞게 바꾼다.
- **불리언 뒤에는 `clean()`.** 면이 정확히 포개진 두 솔리드(거울 · 대칭 회전체)를 합치면 OCC 가
  부피가 음수인 솔리드를 내놓는다(실측). 평가기가 결과마다 `is_valid` 와 부피를 본다.
- `import_step` 노드의 `file` 은 작업물 id 다. 코어는 경로를 모르고 `resolve_file` 콜백으로 받는다.
- **편집기의 노드 목록은 `frontend/src/modules/cad/recipeSpec.ts` 다.** 서버에 연산을 더하면 거기
  한 항목을 더한다 — `recipeSpec.test.ts` 가 서버 `schema.py` 의 op 리터럴과 대조한다.
- 3D 에서 고른 엣지는 **위치(중점)**로 적는다(`EdgeNear`). 인덱스는 형상을 조금만 고쳐도 바뀐다.
  면을 고르면 그 면의 중심 · 법선이 `PlaneSpec.origin/normal` 이 된다. 미리보기는 `/cad/recipe/mesh`
  (면 · 엣지 단위)이고 결과 화면은 glTF — 편집기만 선택이 필요하다.

## 시험 규격

- 시편 · 시험 지그 · 해석 조건의 **프리셋**은 한 모양(`core/specimens/presets.py`)이고 두 곳에 있다
  (ADR 0006): 공개 규격(ASTM · ISO)은 `core/specimens/data/<시험>.json`, 사내 규격은 DB
  (`specimen_presets`, 관리자). **회사 · 고객 규격을 저장소에 넣지 않는다** — 저장소가 공개다.
- 공개 규격의 값을 고치면 `source` 도 고치고, 규격서와 대조했으면 `verified: true`. 데이터 파일의
  프리셋은 전부 `tests/unit/test_core_specimens.py` 가 그려 보고 조건까지 검증한다.
- 지그 생성기는 시편 템플릿과 **같은 규칙 함수**(`specimens.bending`)를 쓴다. 코어는 DB 를 모르므로
  서버가 고른 규격의 규칙을 `JigOptions.bending_setup` 에 값으로 채운다(`works._jig_options`).

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
- **레시피가 가리키는 것은 들어오는 자리에서 본다** — `component` 의 `work:<id>` 와 `import_step` 의
  작업물 id(`cad.services.require_references`). `/cad` 라우터는 의존성으로 걸려 있고, 그 밖에서
  레시피를 받는 끝점(작업 저장 · DOE · 닮은 형상)은 직접 부른다. 새 끝점이 레시피를 받으면 같이 부른다 —
  안 그러면 남의 비공개 작업 id 하나로 그 작업의 STEP 을 받아 갈 수 있다(2026-10-04 점검).
- 스키마를 바꿨으면 `python scripts/export_openapi.py` 와 `npm run api:types` 를 함께 돌린다.
- **만드는 일은 전부 작업(Job)이다.** 지그 생성은 `POST /works/jig-from-part` 가 지그 작업을 만들고
  `Job(kind="jig")` 을 걸어 202 로 돌아온다(끝나면 `…/jig-runs/{job}/adopt` 가 첫 버전으로). 워커(`python -m app.worker`)가 DB 큐에서 집어 돌리고, 화면은 `GET /api/jobs/{id}`
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

## 화면 문구

화면에 보이는 글자는 **격식체**로 쓴다(2026-10-04 사용자 요청 — 구어 표현이 너무 많았다). 화면에
그대로 뜨는 백엔드 문자열(오류 메시지 · 검증 메시지 · 조건 사양의 레이블 · 닮음 이유 · 도면 속 글자)도
같다. 주석 · 독스트링 · 로그 · `Field(description=…)` 는 이 규칙 밖이다.

- 레이블 · 버튼 · 탭 · 표 머리글 · 선택지는 **명사형**(`삭제` · `복원` · `다운로드` · `생성 중…`).
- 설명 · 안내 · 빈 상태 · 툴팁 · 오류는 **합니다체** 문장, 마침표로 끝낸다. 지시는 `~하십시오`, 확인
  창은 `~하시겠습니까?`. `~한다` 평서체 · 구어 어미는 쓰지 않는다.
- 줄표(—)로 문장을 이어 붙이지 않는다 — 문장을 나누거나 쌍점 · 괄호. 주어를 「나 · 남 · 사람」 으로
  쓰지 않는다(`본인` · `다른 사용자` · `사용자`).
- 조사는 붙여 쓴다(`STEP에서` · `DOE가`). 화면 요소 · 사용자가 붙인 이름은 작은따옴표 ‘’ 로.
  문장 안의 나열은 쉼표, 짧은 레이블의 짝은 붙인 가운뎃점(`보기·측정`).
- 용어는 표준 용어로 — 태그(꼬리표 아님) · 등록(승격 아님) · 검색 · 필터 · 선택 · 삭제 · 복원 ·
  다운로드 · 업로드 · 내보내기 · 생성 · 수정 · 조회 · 작성자 · 생성일 · 수정일 · 페이지 · 행 · 위치 ·
  간극 · 핸들 · 솔리드 · 체적 충전율 · 유사 형상. 도메인 용어(도면 · 피처 · 스케치 · 지그 · 부품 ·
  조립 · 버전 · 템플릿 · 휴지통 · 사본 · 변수 · 설계점 · 선택 그룹)는 그대로.
- 문구를 바꾸면 그것을 찾는 시험(vitest 의 `getByText` · `getByRole({ name })`, pytest 의 메시지
  비교)도 함께 바꾼다. 로직이 비교하는 문자열(탭 값 · 예약어 `전역` · 백엔드로 보내는 값)은 레이블과
  떼어 둔다.

## 개발 서버와 워커

`run.py` 는 개발에서 워커를 **watchfiles 로** 띄운다 — `app/` 이 바뀌면 워커가 다시 뜬다. uvicorn 의
reload 는 API 만 새로 띄우기 때문에, 워커를 그냥 자식으로 두면 모델을 바꾼 뒤 옛 워커가 매 루프
SELECT 에서 죽어 「작업이 queued 에서 안 움직인다」 가 된다(실측, 2026-09-18). **마이그레이션을
돌렸으면 서버를 다시 띄운다** — 그 전에 뜬 워커는 watchfiles 가 없는 옛 run.py 일 수 있다.

DOE 형상은 **다른 프로세스**가 만든다(`doe.services._build_shape`, forkserver, `DOE_WORKERS`).
그 함수에는 사전 · 목록만 넘기고 DB 객체(`DoePoint` 등)를 넘기지 않는다 — 피클되지 않거나, 되더라도
세션 밖에서 엉뚱하게 읽힌다. DB 에 적는 일(상태 · 점 파일 · 표)은 작업 프로세스가 결과를 받아 한다.
시험은 기본 한 프로세스(`tests/conftest.py` 의 `DOE_WORKERS=1`)이고, 나눠 만드는 길은 그것을
켜는 시험 하나가 한 프로세스와 결과를 견준다.

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

## 배포와 릴리스

**번들은 태그에서 나온다.** `git tag v0.1.0 && git push origin v0.1.0` → Actions 가
`ci.yml` 전체를 먼저 돌리고(통과해야 한다), `deploy/build_bundle.sh` 로 tar.gz 하나를 만들어
릴리스에 붙인다. 검증을 릴리스 쪽에 한 벌 더 적지 않는다 — 두 벌이 되면 한쪽만 고쳐지고,
그때부터 「CI 는 통과인데 릴리스는 다른 것을 본다」 가 된다.

- 받는 PC 는 저장소를 안 받는다. `deploy/pc/fetch-release.{sh,ps1,bat}` 이 릴리스를 받아
  체크섬까지 본다. 저장소가 공개라 토큰은 필요 없다 — 비공개 포크로 쓸 때만 `GH_TOKEN`.
- 손으로 만들려면 `./deploy/build_bundle.sh v0.1.0` (리눅스 · apptainer · npm 필요, 몇 분).
  **Windows 에서는 못 만든다** — Apptainer 가 리눅스 전용이라 CI 가 그 일을 한다.
- 번들에 무엇이 들어가야 하는지는 `release.yml` 의 「번들이 온전한가」 가 지킨다. 새 파일을
  `build_bundle.sh` 에 더했으면 그 목록에도 더한다 — 빠진 파일은 **서버에서** 드러난다.
- **문서 · 안내 문구에서 env 는 `sudo` 뒤에 쓴다** — `sudo X=… ./deploy.sh`. `X=… sudo ./deploy.sh` 는
  우분투 기본 sudo(`env_reset`)가 값을 **조용히 버려** 그 명령이 아무 일도 안 한 것이 된다(24.04 운영
  서버에서 확인, 2026-10-05).
- 서버 쪽 명령(`deploy.sh setup · update · status · backup · db-*`)의 정본은
  `deploy/README_OPERATOR.md` 다. 쉬운 순서는 `deploy/쉬운-설치.md`.
- `.gitattributes` 가 `*.sh · *.def · *.template` 을 LF 로 고정한다. Windows 에서 클론해
  만지면 CRLF 가 섞이고, 그것은 서버에서 `bad interpreter: bash^M` 로만 보인다.

## 문서

- 판단이 갈렸던 결정은 `docs/adr/NNNN-제목.md` 에 남긴다 — 결정 · 배경 · 대안 · 결과.
- 실측으로 드러난 함정은 근거와 함께 적는다. "이렇게 하세요" 보다 "이렇게 안 하면 이런 일이
  났다" 가 다음 사람에게 유용하다.
