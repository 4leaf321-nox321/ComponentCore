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

## 시험
```bash
cd mcp_server && ./venv/bin/pip install pytest
cd .. && mcp_server/venv/bin/python -m pytest mcp_server/tests     # 가이드 · 언래핑
cd backend && .venv/bin/python -m pytest tests/api/test_mcp_tools.py  # 진짜 앱에 붙여서
```
