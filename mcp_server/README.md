# CompCore MCP 서버

AI(Claude Code · Claude Desktop · 다른 MCP 클라이언트)가 **내 작업**에서 부품을 그리고 지그를
만들게 하는 도구. 플랫폼이 AI 를 부르지 않는다 — AI 가 이 서버를 도구로 물고, 사용자의 개인
토큰으로 백엔드에 붙는다.

## 설치 · 실행
```bash
cd mcp_server
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
PLATFORM_API_BASE=http://127.0.0.1:8061 ./venv/bin/python server.py
# → streamable-http, 기본 http://127.0.0.1:8062/mcp
```

**개발에서는 이 명령을 칠 일이 없다.** `backend` 의 `python run.py` 가 이 venv 가 있으면 MCP 서버를
자식으로 함께 띄운다(개발 백엔드 8061 → MCP 8062, Ctrl+C 로 같이 내림). `MCP_DEV=0` 이면 안 띄운다.
포트는 백엔드 +2 (8060 운영 · 8061 개발 · 8062 MCP).

## Claude Code 등록 (사용자별 토큰)
1. 화면 「내 정보」 → 개인 토큰 발급 — 이름(예: Claude Code) · 범위 `read` + `write`. 토큰은 한 번만 보인다.
2. ```bash
   claude mcp add --transport http compcore http://127.0.0.1:8062/mcp \
     --header "Authorization: Bearer compcore_pat_…"
   claude mcp list   # compcore: … - ✔ Connected
   ```
3. Claude 에게 "80×50×10 판에 모서리 M6 구멍 넷, 이름은 베이스" 라고 하면 `get_guide` →
   `recipe_check` → `create_work` 로 내 작업에 들어간다. 화면의 내 작업에서 3D 를 보고 승격한다.

토큰은 **저장소에 안 넣는다.** `claude mcp add` 의 기본 범위(local)는 이 PC 의 사용자 설정에만 남는다.

## 도구
| 도구 | 하는 일 |
| --- | --- |
| `get_guide(topic?)` | 레시피 규칙 · 작업 순서 · 지그 읽는 법 — **먼저 부른다** |
| `recipe_schema` | 피처 종류 · 칸(JSON Schema) · 템플릿 넷 |
| `recipe_check(recipe)` | 만들어 본다 — 통과하면 요약, 실패하면 어느 피처가 왜 |
| `list_works` · `get_work` · `list_versions` · `get_version` | 내 작업 읽기 |
| `create_work` · `save_version` · `restore_version` | 새 작업(부품) · 새 버전(출처 ai) · 되돌리기 |
| `jig_options` · `run_jig` · `list_jig_runs` · `get_job` | 지그 생성과 결과 |
| `promote_part` · `promote_jig` | 카탈로그에 올리기 — 사용자가 시킬 때만 |
| `list_parts` · `get_part` · `copy_part_to_work` · `list_jigs` · `get_jig` | 카탈로그 |

### 기준정보(온톨로지) — `ontology.py` · `ontology_links.py`

StandardPlatform `6e5a773` 의 MCP 도구 72개를 그대로 옮겼다(ADR 0008) — 정의(`ontology_schema` ·
`ontology_import` …), 객체(`objects_list` · `object_resolve` · `object_create` …), 일괄 · 묶음
(`objects_import` · `bundle_import` · `bulk_edit`), 관계(`relation_add` · `relations_import`),
둘러보기(`graph_neighbors` · `quality_report` · `audit_recent`), 데이터 작업(`task_status` ·
`task_apply` …), 데이터 소스(`datasource_sync` …), RDF(`rdf_query`), 지표(`metric_*`).
**`ontology_guide` 를 먼저 부른다**(안내서 `guide/ONTOLOGY.md`).

| SP 에서 | 여기서 | 까닭 |
| --- | --- | --- |
| `search` | `object_search` | 작업 · 부품 찾기 `search` 가 이미 있다 |
| `job_status` · `job_apply` · `jobs_list` · `job_cancel` | `task_*` | 형상 작업(`get_job` · `cancel_job`)과 다른 큐다 — 경로도 `/api/tasks` |
| `get_guide` | `ontology_guide` | 안내서가 둘이다 |
| `platform_profile` · `platform_profile_update` | 없음 | 설치의 자기소개 API 를 안 들였다 |
| `extensions_schema` · `extension_call` | 없음 | 확장 모듈 기제를 안 들인다(AGENTS.md) |

CompCore 에만 있는 것: `ontology_links(kind, id)` · `ontology_link` · `ontology_unlink` — 부품 ·
지그 화면의 「기준정보」 칸(관계 종류마다 한 줄 · 이름 추천). 잇는 사람은 그 부품의 주인 · 관리자다.

`ontology.py` · `guide/ONTOLOGY.md` · `tests/test_ontology_sp.py` 는 **손으로 고치지 않는다** —
`port_from_sp.py` 가 SP 의 파일에서 다시 만든다(쓰는 법은 그 파일 머리에).

## 시험
```bash
cd mcp_server && ./venv/bin/pip install pytest
cd .. && mcp_server/venv/bin/python -m pytest mcp_server/tests     # 가이드 · 언래핑
cd backend && .venv/bin/python -m pytest tests/api/test_mcp_tools.py  # 진짜 앱에 붙여서
```
