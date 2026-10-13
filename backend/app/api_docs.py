"""공개 API 의 **한 장짜리 안내** — `/api/docs` 가 이것을 읽는다.

정본을 둘로 두지 않으려고 여기 한 벌만 적는다: 사람이 읽는 긴 설명은
`docs/공개-API.md`, 기계가 읽는 목록은 `/api/openapi.json` 이고, **둘 다 이 파일에서
나온다**(문서가 코드에서 자란다). 엔드포인트마다의 설명은 그 라우터의 독스트링이다 — 여기
다시 적지 않는다.
"""

from __future__ import annotations

from typing import Any

from app.shared.errors import code

#: 머리말에 보일 **진짜 코드 하나.** 손으로 이어 적으면 접두사를 바꾸는 날 문서만 거짓말을
#: 한다 — 그래서 코드를 만드는 함수에서 받아 온다(시험이 이것을 못 박는다).
_SAMPLE_CODE = code("DOE", 10)

#: 묶음마다 무엇을 하는 곳인가. `/api/docs` 의 큰 제목 밑에 그대로 나온다.
TAGS: list[dict[str, Any]] = [
    {
        "name": "auth",
        "description": (
            "로그인과 **개인 토큰(PAT)**. 기계는 늘 PAT 으로 붙는다 — 토큰은 "
            "`Authorization: Bearer <토큰>` 한 줄이다.\n\n"
            "범위: `read`(조회) · `write`(만들고 고치기) · "
            "`act_for_others`(**대행** — 남의 이름으로 만든다). 사람 세션에는 범위를 걸지 "
            "않는다(그 사람의 권한이 이미 한계다)."
        ),
    },
    {
        "name": "cad",
        "description": (
            "**레시피**(형상을 만드는 연산 트리)를 검증 · 평가 · 질의한다. 이 플랫폼의 정본은 "
            "STEP 이 아니라 레시피다 — STEP · glTF 는 거기서 나온 사본이다.\n\n"
            "여기 것은 대부분 **아무것도 저장하지 않는다**(POST 이지만 읽기다)."
        ),
    },
    {
        "name": "doe",
        "description": (
            "**실험계획** — 치수와 해석 조건을 훑어 형상 여러 벌을 만들고, 자기 설명적인 폴더 "
            "하나로 해석 플랫폼에 넘긴다.\n\n"
            "기계가 지휘할 때 쓰는 한 벌: `POST /doe/run`(만들고 · 기다리고 · 내보낸다) → "
            "`GET /doe/{id}/status` → `POST /doe/{id}/release`(다 읽었다). 재시도에는 "
            "`idempotency_key` 를 준다.\n\n"
            "**해석 결과는 여기로 돌아오지 않는다** — 푸는 쪽이 들고 거기서 본다."
        ),
    },
    {
        "name": "works",
        "description": (
            "**내 작업** — 비공개로 그리는 자리. 버전마다 레시피와 해석 조건이 붙고, "
            "「승격」 하면 공용 부품 · 지그 카탈로그로 나간다. 시스템 관리자는 목록의 "
            "`owner`(all · 사람 id)로 남의 작업을 찾는다."
        ),
    },
    {"name": "parts", "description": "공용 **부품** 카탈로그(불변 버전)."},
    {"name": "jigs", "description": "공용 **지그** 카탈로그(불변 버전)."},
    {"name": "templates", "description": "레시피 **템플릿** — 변수만 채워 쓰는 밑그림."},
    {
        "name": "specimens",
        "description": (
            "**시험 규격** — 공개 규격(ASTM · ISO, 코드)과 사내 규격(DB, 관리자)의 프리셋. "
            "규격으로 시편 · 시험 지그 · 해석 조건이 붙은 내 작업을 만든다."
        ),
    },
    {
        "name": "search",
        "description": (
            "여러 목록을 가로지르는 찾기 — **닮은 형상**(최신 버전의 형상 색인끼리 견준다). "
            "이름 · 꼬리표 찾기는 각 목록의 `q` 가 한다."
        ),
    },
    {
        "name": "jobs",
        "description": (
            "**작업 큐** — 형상 평가 · 지그 생성 · DOE 가 여기서 돈다. 걸면 즉시 돌아오고, "
            "끝났는지는 이 묶음이나 각 모듈의 `status` 로 본다."
        ),
    },
    {
        "name": "materials",
        "description": (
            "**물성** — MatNexus 에서 골라 온다. 값을 해석하지 않고 payload 를 통째로 나른다 "
            "(「어느 것이 영률인가」 는 솔버를 아는 쪽의 일이다). 못 닿으면 관리자가 올려 둔 "
            "카탈로그로 넘어가고, **넘어갔다는 사실을 답이 말한다**(`fallback`)."
        ),
    },
    {
        "name": "voc",
        "description": (
            "**VOC 게시판** — 불편한 점 · 필요한 기능을 앱 안에서 남긴다. 로그인한 누구나 "
            "보고, 한 건은 등록 → 접수 → 처리 중 → 해결 → 종료(또는 반려)를 거치며 누가 언제 "
            "무슨 말로 옮겼는지 이력에 남는다. 옮길 수 있는 곳은 상세의 `allowed` 가 말한다."
        ),
    },
    # --- StandardPlatform 에서 들인 것(ADR 0008) ---
    {
        "name": "ontology",
        "description": (
            "**온톨로지 정의** — 묶음 · 타입 · 속성 · 관계 종류 · 인터페이스를 데이터로 "
            "정의한다. 정의하면 목록 · 상세 · 트리 화면이 생긴다. "
            "`GET /ontology/schema` 하나가 전부를 돌려준다."
        ),
    },
    {
        "name": "objects",
        "description": (
            "**온톨로지 객체** — 타입의 행. 만들기 · 고치기 · 관계 · 별칭 · 이력 · 일괄 "
            "입력(계획을 보고 적용) · 내보내기. 부서가 소유하고, 고치는 것은 소유 부서의 "
            "관리자다."
        ),
    },
    {"name": "graph", "description": "객체 · 관계를 그래프로 — 이웃 · 경로 · 개요."},
    {"name": "rdf", "description": "온톨로지 · 객체의 RDF 내보내기와 SPARQL 묻기(읽기만)."},
    {"name": "objectsearch", "description": "온톨로지 객체 전체 찾기 — 타입을 가로질러."},
    {
        "name": "core",
        "description": (
            "**코어 API** — 바깥 시스템이 공개된 기준정보를 당겨 가는 창구(`core:read`). "
            "지난번 이후 바뀐 것 · 사라진 것 · 관계를 `since` · `next` · `as_of` 로."
        ),
    },
    {
        "name": "datasources",
        "description": (
            "**데이터 소스** — 바깥 시스템(OData · REST · 파일)에서 읽어 온톨로지를 채운다."
        ),
    },
    {
        "name": "tasks",
        "description": (
            "**데이터 작업** — 일괄 입력 · 내보내기 · 묶음 · 동기화처럼 오래 걸리는 일. "
            "계획 → 사람 확정 → 적용. 형상 작업(`jobs`)과 큐가 다르다."
        ),
    },
    {
        "name": "bundles",
        "description": "정의와 객체를 한 묶음 파일로 내보내고 들인다(계획 먼저).",
    },
    {
        "name": "review",
        "description": "**검토함** — 사람의 판단을 기다리는 일을 한 곳에 모은다.",
    },
    {
        "name": "metrics",
        "description": "**지표 · 분석 · 경보** — 기록을 미리 세어 두고 묻는다.",
    },
    {
        "name": "webhooks",
        "description": "커밋된 변경을 바깥에 알린다 — 서명 · 재시도 · 보낸 기록.",
    },
    {
        "name": "workspaces",
        "description": "**부서** — 트리형 조직도, 멤버와 역할. 객체의 소유 단위.",
    },
    {
        "name": "files",
        "description": "첨부 — 내용 해시로 중복을 없애고 부서 단위로 권한을 본다.",
    },
    {
        "name": "notifications",
        "description": "알림 — 지켜보는 객체가 바뀌거나 작업이 끝났을 때.",
    },
    {"name": "audit", "description": "감사 기록과 접근 로그 — 무엇이 바뀌었고 누가 했나."},
    {"name": "accounts", "description": "계정과 가입 승인. 관리자용."},
    {"name": "server", "description": "서버 설정(상한 · 보관 기한)과 상태. 관리자용."},
    {"name": "system", "description": "살아 있나 · 버전."},
]

DESCRIPTION = f"""\
CAD 를 **DOE 로 만드는** 플랫폼의 API. 사람이 쓰는 화면과 AI 가 쓰는 MCP 가 **모두 이 API 를
부른다** — MCP 는 이것을 감싸는 얇은 층이라, MCP 에만 있는 편의는 없다.

### 붙는 법

    curl -H "Authorization: Bearer <PAT>" http://<호스트>/api/works

PAT 은 화면의 「내 정보 → 토큰」 에서 만든다. 쓰기에는 `write` 범위가 필요하고, 남의 이름으로
만들려면(대행) `act_for_others` 가 필요하다.

### 약속

- **오류는 한 모양이다**:
  `{{"error": {{"code": "{_SAMPLE_CODE}", "message": "…", "details": {{…}}}}}}`.
  `code` 는 안 바뀐다 — 기계는 문구가 아니라 그것으로 가른다.
- **목록은 한 모양이다**: `{{"items": [...], "total": n, "limit": n, "offset": n}}`.
- **치수는 mm, 각도는 도(°)** 다. 물성 payload 만 예외로 MatNexus 의 단위를 그대로 쓴다.

자세한 것은 저장소의 `docs/공개-API.md`.
"""
