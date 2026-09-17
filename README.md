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

## 기술 스택

| 층 | 도구 |
| --- | --- |
| 코어 | Python 3.12 · [build123d](https://build123d.readthedocs.io/) 0.11 (OpenCascade) |
| 백엔드 | FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · PyJWT · bcrypt |
| 프론트 | React 19 · TypeScript · Vite · Tailwind 4 · shadcn · three.js (glTF 뷰어) |
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
.venv/bin/python run.py         # http://127.0.0.1:8051 (개발은 운영 포트 8050 의 +1)
```

API 문서: <http://127.0.0.1:8051/api/docs>

### 3. 프론트

```bash
cd frontend
npm install
npm run api:types               # backend/openapi.json → src/shared/api/schema.d.ts
npm run dev                     # http://localhost:5250 — /api 는 8051 로 프록시
```

`npm run build` 를 하면 백엔드 한 프로세스가 `frontend/dist` 까지 서빙한다 — 배포 형태가 그것이다.

### 서버 없이 코어만

```bash
cd backend
.venv/bin/python scripts/generate_jig.py                 # 시연 제품(L 브래킷) → out/
.venv/bin/python scripts/generate_jig.py part.step -o out/
```

`out/jig.step` (지그), `out/jig-assembly.step` (지그 + 제품), `out/jig.glb` · `out/product.glb` (미리보기)
가 나온다.

## 화면

- **지그 프로젝트** — 제품 STEP 을 올리거나 기본 도형을 고르고, 옵션(판 여유 · 받침 수 · 클램프
  수 …)을 바꿔 「지그 생성」. 결과는 3D(제품 파랑 · 지그 회색) · 단계별 시간 · 계획 · 간섭 표 ·
  STEP 내려받기.
- **CAD 작업대** — 제품 파일 없이 도형을 그려 STEP 으로 받거나, 그 도형으로 바로 프로젝트를 만든다.
- **계정 / 서버** — 시스템 관리자. 계정은 관리자가 만들고 임시 비밀번호는 한 번만 보인다.

## 검증

```bash
cd backend && .venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/python -m pytest && .venv/bin/alembic check
cd ../frontend && npm run build && npm test && npm run lint
```

## 포트

플랫폼마다 10씩 벌린다: StandardPlatform 8040 · **AutoJigGenerator 8050** (개발 8051, Vite 5250).
