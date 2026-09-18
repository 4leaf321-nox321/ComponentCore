# AutoJigGenerator

제품 STEP 을 올리면 지그(fixture)를 자동으로 설계해 STEP 으로 돌려주는 플랫폼.
제품 파일이 없어도 기본 도형(상자 · 원기둥 · 구멍 뚫린 판 · L 브래킷)을 그려 지그를 잡아 볼 수 있다.

    제품 STEP
        ▼  Geometry Understanding   크기 · 부피 · 면 수, 바닥 z=0 으로 정규화
        ▼  Feature Recognition      바닥 · 윗면 · 옆면 · 수직 구멍
        ▼  Fixture Planning         3-2-1: 받침 · 로케이터(핀 / 레스트) · 클램프 자리
        ▼  Support · Locator · Clamp  build123d 로 부품 생성
        ▼  Jig 자동 생성            베이스 플레이트 + 부품 조립
        ▼  간섭 검사                부품 - 제품 · 부품 - 부품 겹침 부피
        ▼  STEP (+ glTF 미리보기)

생성은 **작업(Job)** 으로 걸리고 워커가 돌린다. 「내 작업」 에 종류 · 상태 · 산출물이 쌓인다.
로드맵은 [docs/로드맵.md](docs/로드맵.md).

## 기술 스택

| 층 | 도구 |
| --- | --- |
| 코어 | Python 3.12 · [build123d](https://build123d.readthedocs.io/) 0.11 (OpenCascade) |
| 백엔드 | FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · PyJWT · bcrypt |
| 프론트 | React 19 · TypeScript · Vite · Tailwind 4 · shadcn · three.js (glTF 뷰어) |
| AI 연결 | MCP 서버(`mcp_server/`, streamable-http) — Claude Code · Desktop 이 개인 토큰으로 붙는다 |
| 검증 | ruff · mypy(strict) · pytest / oxlint · vitest |

구조와 규칙은 [AGENTS.md](AGENTS.md), 설계 결정은 [docs/adr/](docs/adr/).

## 개발 환경

### 1. PostgreSQL

`autojig` 와 `autojig_test` 데이터베이스가 있어야 한다.

```bash
psql -U postgres -c "CREATE DATABASE autojig"
psql -U postgres -c "CREATE DATABASE autojig_test"
```

### 2. 백엔드

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env            # DATABASE_URL 을 맞춘다
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_install.py --email admin --password '...' --no-force-change
.venv/bin/python run.py         # http://127.0.0.1:8061 (개발은 운영 포트 8060 의 +1)
                                 # 작업 워커(python -m app.worker)를 자식으로 함께 띄운다
```

워커 없이 요청 안에서 돌리려면 `.env` 에 `JOBS_INLINE=1`. 운영에서는 워커를 별도 프로세스로
띄운다(`python -m app.worker`, 여럿이면 그만큼 동시에 돈다).

API 문서: <http://127.0.0.1:8061/api/docs>

### 3. 프론트

```bash
cd frontend
npm install
npm run api:types               # backend/openapi.json → src/shared/api/schema.d.ts
npm run dev                     # http://localhost:5230 — /api 는 8061 로 프록시
```

`npm run build` 를 하면 백엔드 한 프로세스가 `frontend/dist` 까지 서빙한다 — 배포 형태가 그것이다.

### 4. AI 붙이기 (MCP)

```bash
cd mcp_server && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
```
그 뒤 `python run.py` 가 MCP 서버(8062)를 함께 띄운다. 화면 「내 정보」 에서 개인 토큰을 발급하고:
```bash
claude mcp add --transport http autojig http://127.0.0.1:8062/mcp \
  --header "Authorization: Bearer autojig_pat_…"
```
Claude 에게 "80×50×10 판에 모서리 M6 넷, 이름은 베이스" 라고 하면 내 작업에 출처 「AI」 버전이
생긴다. 자세한 것은 [mcp_server/README.md](mcp_server/README.md).

### 서버 없이 코어만

```bash
cd backend
.venv/bin/python scripts/generate_jig.py                 # 시연 제품(L 브래킷) → out/
.venv/bin/python scripts/generate_jig.py part.step -o out/
```

`out/jig.step` (지그), `out/jig-assembly.step` (지그 + 제품), `out/jig.glb` · `out/product.glb` (미리보기)
가 나온다.

## 화면

구조는 **내 공간에서 그려서, 승격으로 내놓는다**.

- **그리기** — 리본(파일 · 스케치 · 입체 · 조합 · 마감 · 배치 · 보기)에서 레시피(연산 트리 JSON)를
  그린다. 빈 화면에서 시작하거나 「파일」 탭에서 템플릿 · 기존 작업 · STEP 을 연다. 3D 에서 면 · 엣지를
  고르고, 측정 창으로 거리 · 각도 · 지름 · 두께를 재며, STEP · STL · DXF · SVG 로 받는다. 「내 작업으로 저장」 전에는 아무것도
  남지 않는다.
- **내 작업** — 나만 보는 문서. 부품 탭(버전 · 되돌리기 · STEP 올리기 · 카탈로그로 승격)과 지그 탭
  (옵션 · 지그 생성 · 실행 기록 · 결과 3D · 지그로 승격).
- **실행 기록** — 내가 건 작업(부품 평가 · 지그 생성)과 산출물.
- **템플릿** — 그리기의 출발점을 모아 둔 곳. **내 것**과 **공용** 두 자리가 있고 스위치 하나로
  오간다(버전은 없다 — 고친 결과는 작업으로 간다). 남의 공용 템플릿은 「내 것으로 복사」 해서 쓴다.
- **부품 · 지그** — 공용 카탈로그. 승격된 불변 버전. 지그는 어느 부품 버전의 지그인지 함께 적힌다.
  고치려면 「내 공간으로 복사」 → 고침 → 다시 승격.
- **계정 / 서버** — 시스템 관리자. 계정은 관리자가 만들고 임시 비밀번호는 한 번만 보인다.

## 검증

```bash
cd backend && .venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/python -m pytest && .venv/bin/alembic check
cd ../frontend && npm run build && npm test && npm run lint
```

## 포트

플랫폼마다 10씩 벌린다: StandardPlatform 8040 · (예약) PartTrace 8050 · **AutoJigGenerator 8060** (개발 8061, Vite 5230).
정본 표는 `StandardPlatform/docs/새-플랫폼-만들기.md` 3.6.
