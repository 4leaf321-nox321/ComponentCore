# 개발 지침

이 저장소에서 코드를 고칠 때 지키는 규칙. **이 파일이 정본이다.** `CLAUDE.md` 는 이 파일을
가리키기만 한다.

## 이 저장소가 무엇인가

**AutoJigGenerator — 제품 STEP 에서 지그(fixture)를 자동으로 만드는 독립 플랫폼.**

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

## 이름과 식별자

- 설치 이름은 `.env` 가 덮을 수 있다(`APP_NAME` · `APP_SLUG`). 코드는 `get_settings().app_name`
  으로 읽고 `branding.py` 에서 import 하지 않는다 — `config.py` 만 예외.
- `APP_SLUG` 에서 DB 이름과 refresh 쿠키 이름이 나온다. 같은 서버의 다른 플랫폼과 겹치면
  **번갈아 로그아웃**되고 그 원인은 코드 어디에도 없다. 기본값 `autojig`.
- **포트는 8050 (개발 8051 · Vite 5250).** 플랫폼마다 10씩 벌린다 — StandardPlatform 8040.
- 오류 코드는 `errors.code("MODULE", n)` 로만 만든다(`AJG-JIGS-0003`). 손으로 이으면
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
- **지그 생성은 지금 동기다**(`jigs/services.execute_run`). 요청 스레드에서 파이프라인이 다
  돈다. 큰 조립체를 받기 시작하면 워커로 옮기고 화면은 폴링으로 — 그때도 API 모양은 안 바뀐다.
- 결과 파일(glTF · STEP)은 토큰이 있어야 받는다. 화면은 `fetchBlob` 으로 받아 Blob URL 을
  뷰어에 준다 — `<a href>` 나 `<img src>` 에는 access 토큰이 실리지 않는다.

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

## 검증

고치고 나서 이것을 돌린다. **마이그레이션을 만들었으면 그 자리에서 개발 DB 에 올린다**
(`alembic upgrade head`).

```bash
cd backend
.venv/bin/ruff format . --config pyproject.toml
.venv/bin/ruff check . --config pyproject.toml
.venv/bin/mypy
.venv/bin/python -m pytest
.venv/bin/python -m alembic check
cd ../frontend && npm run build && npm test && npm run lint
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
