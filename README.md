# CompCore

부품(Component)을 가운데 두고 도는 플랫폼 — STEP 을 올리거나 직접 그린 도면에서
지그(fixture)를 자동으로 설계하고, 변수를 훑어(DOE) 해석으로 넘긴다.
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

`compcore` 와 `compcore_test` 데이터베이스가 있어야 한다.

```bash
psql -U postgres -c "CREATE DATABASE compcore"
psql -U postgres -c "CREATE DATABASE compcore_test"
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
claude mcp add --transport http compcore http://127.0.0.1:8062/mcp \
  --header "Authorization: Bearer compcore_pat_…"
```
Claude 에게 "80×50×10 판에 모서리 M6 넷, 이름은 베이스" 라고 하면 내 작업에 출처 「AI」 버전이
생긴다. AI 는 3D 를 못 보므로 **그림**(`recipe_views` — 등각 · 정면 · 윗면 · 우측 은선 투영)으로
확인하고, 엣지 · 면 좌표는 **묻고**(`recipe_find`), 거리는 **재고**(`recipe_measure`), 고칠 때는
**연산 몇 개**로(`patch_work`) 한다. 볼트 · 핀 · 스페이서는 노드(`bolt` · `pin` · `standoff`)로
놓고, 조립은 `place_on` · `assemble_jig_on_part` 로 자리를 잡는다. 자세한 것은
[mcp_server/README.md](mcp_server/README.md).

### 5. 서버에 배포

```bash
./deploy/build_bundle.sh v0.1.0      # 프론트 빌드 → Apptainer SIF → tar.gz 하나 (몇 분)
scp release/compcore-v0.1.0.tar.gz <계정>@<서버>:~/
# 서버에서
tar xzf compcore-v0.1.0.tar.gz && cd compcore-v0.1.0
sudo ./deploy.sh setup               # 물어보며 prepare → install (또는 prepare/install 따로)
```

**보통은 손으로 안 만든다.** 태그를 밀면 GitHub Actions 가 CI 를 통과시킨 뒤 번들을 만들어
릴리스에 붙인다 — `git tag v0.1.0 && git push origin v0.1.0`. 받는 PC 는
[deploy/pc/](deploy/pc/) 의 스크립트로 받는다(비공개 저장소라 `GH_TOKEN` 이 필요하다).

한 프로세스가 API 와 화면을 같이 서빙하고, 워커(`compcore-worker`)와 MCP 서버(`compcore-mcp`)가
따로 뜬다. **실험계획의 공유 폴더**는 `DOE_HOST_DIR` 로 정한다 — 해석(ANSYS)이 읽는 자리라
안 정하면 DOE 를 만들 때 거절된다. 자세한 것은 [deploy/README_OPERATOR.md](deploy/README_OPERATOR.md)
(쉬운 순서는 [deploy/쉬운-설치.md](deploy/쉬운-설치.md)).

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

- **새 작업** — 리본(파일 · 스케치 · 입체 · 조합 · 마감 · 배치 · 보기)에서 레시피(연산 트리 JSON)를
  그린다. 빈 화면에서 시작하거나 「파일」 탭에서 템플릿 · 기존 작업(사본) · STEP 을 연다. 3D 에서 면 · 엣지를
  고르고, 측정 창으로 거리 · 각도 · 지름 · 두께를 재며, STEP · STL · DXF · SVG 로 받는다. 저장은 늘
  **새 작업**(부품 | 지그)을 만든다 — 기존 작업을 덮어 고치는 건 내 작업 › 수정에서. 저장 전에는
  아무것도 남지 않는다.
- **내 작업** — 나만 보는 문서. 머리에는 작업 자체의 일(실험계획 만들기 · 공용 부품/지그로 승격 ·
  지우기), 도면 탭 도구줄에는 도면의 일(수정 · STEP 받기 · 템플릿으로 저장). STEP 올리기는 「수정」
  안 「파일」 탭에서 — 올린 STEP 이 새 버전이 된다.
- **부품에서 지그 생성** — 지그의 두 번째 시작점(첫째는 새 작업에서 그리기). 부품(내 작업 또는
  공용)과 **형식**을 고르면 규칙으로 놓고 간섭을 검사해 **지그 작업**을 만든다: 판 · 클램프 고정
  (3-2-1), 볼트 고정(관통 구멍으로 판에 조임 — 진동 · 충격 시험), 3점 굽힘 픽스처(롤러 둘 + 로딩
  노즈), 낙하 · 충격 자세(고른 면이 아래, 바닥 + 강구/펜). 고르는 순간 같은 규칙이 돌아 3D 로
  미리 보이고, 결과 STEP 이 첫 버전이 되어 거기서 이어서 그린다(변수 · DOE).
- **실행 기록** — 내가 건 작업(부품 평가 · 지그 생성)과 산출물.
- **DOE** — 독립 공간. 대상(부품 · 지그 · 조립)을 고르고 변수에 범위를 주면 인스턴스를 여럿
  만들어 **서버 보관 폴더**에 STEP + 표로 만든다. 다 만들어지면 「공유 폴더로 보내기」 — 해석
  (ANSYS)은 그 폴더를 읽는다. 전체 조합 · LHS(시드로 재현) · CSV. 표에는 바꾼 변수와 파일
  이름만 — 질량 · 크기는 계산하지 않는다(결과는 해석이 낸다). 값은 인자마다 고른 가공 단위
  (기본 0.1 mm)로 맞춘다. 「설정 바꿔 다시 만들기」 로 지난 DOE 의 설정을 채워 새로 만든다.
  만든 형상은 점마다 3D 로 본다 — 하나씩(◀ ▶) · 겹쳐 보기 · 나란히(쪽으로 넘겨 수백 개도).
  한 번에 화면에 올리는 형상 수와 목록 한 쪽의 줄 수도 「서버 › 설정」 에서 바꾼다.
- **찾기 · 꼬리표 · 복제 · 휴지통** — 내 작업 · 공용 부품 · 지그 목록의 찾기 칸, 작업에 꼬리표
  (프로젝트 · 제품군)를 붙여 거르기, 현재 도면으로 복제, 지운 작업 되살리기. MCP `search`.
- **부품 + 지그로 조립** — 부품과 지그 작업을 고르면 맞는 자리에 놓은 조립이 생긴다(생성된 지그는
  그 좌표계로 정확히, 직접 그린 지그는 어림). 부품 높이가 변수라 그대로 DOE 로 훑는다. MCP
  `assemble_jig_on_part`.
  한 번에 만드는 설계점 상한은 관리자가 「서버 › 설정」 에서 바꾼다.
- **변수(파라메트릭)** — 레시피에 이름 붙인 값을 두고, 어느 숫자 칸에서든(피처 · 스케치 도형) `fx` 를 눌러 `=이름` 으로 쓴다. 하나를 고치면
  그것을 쓰는 곳이 모두 따라온다. `align` 으로 한쪽 끝을 고정하면 반대쪽으로만 자란다.
- **템플릿** — 새 작업의 출발점을 모아 둔 곳. **내 것**과 **공용** 두 자리가 있고 스위치 하나로
  오간다(버전은 없다 — 고친 결과는 작업으로 간다). 남의 공용 템플릿은 「내 것으로 복사」 해서 쓴다.
- **부품 · 지그 · 조립** — 부품과 지그는 **서로 관계없는 각자의 도면**이고, 그리는 방법은 같다.
  둘을 함께 놓아 보는 자리가 **조립**이다: 왼쪽 라이브러리에서 가져와 자리 · 회전을 주고,
  구성품의 치수에 조립 변수를 물린다. 변수 · 실험계획은 셋 다 그대로 쓴다.
- **부품 · 지그** — 공용 카탈로그. 승격된 불변 버전. 지그는 어느 부품 버전의 지그인지 함께 적힌다.
  고치려면 「내 공간으로 복사」 → 고침 → 다시 승격.
- **계정 / 서버** — 시스템 관리자. 계정은 관리자가 만들고 임시 비밀번호는 한 번만 보인다.

## 검증

```bash
cd backend && .venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/python -m pytest && .venv/bin/alembic check
cd ../frontend && npm run build && npm test && npm run lint
```

## 포트

플랫폼마다 10씩 벌린다: StandardPlatform 8040 · (예약) PartTrace 8050 · **CompCore 8060** (개발 8061, Vite 5230).
정본 표는 `StandardPlatform/docs/새-플랫폼-만들기.md` 3.6.
