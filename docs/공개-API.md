# 공개 API — 붙는 법과 약속

> 2026-09-24. **사람이 쓰는 화면과 AI 가 쓰는 MCP 가 모두 이 API 를 부른다.** MCP 는 이것을
> 감싸는 얇은 층이라, MCP 에만 있는 편의는 없다 — 그래야 AI 가 아닌 것이 붙는 날 다시 만들지
> 않는다.
>
> 이 문서는 **사람이 읽는 한 장**이다. 기계가 읽는 목록은 `/api/openapi.json` 이고 브라우저로
> 볼 것은 `/api/docs` 다. 둘 다 코드(`backend/app/api_docs.py` + 각 라우터의 독스트링)에서
> 나오므로, 엔드포인트마다의 설명은 여기 옮겨 적지 않는다 — **정본을 둘로 두지 않는다.**

## 1. 붙는 법

```bash
curl -H "Authorization: Bearer <PAT>" http://<호스트>/api/works
```

PAT 은 화면의 **내 정보 → 토큰**에서 만든다. 로그인 세션의 액세스 토큰도 같은 자리에 넣을 수
있지만, 기계는 PAT 을 쓴다(세션은 만료된다).

### 범위 — 토큰에 붙는 울타리

| 범위 | 뜻 |
| --- | --- |
| `read` | 조회 · 레시피 검증 · 미리보기 |
| `write` | 만들고 고치기 — 작업 · 버전 저장 · 지그 생성 · DOE |
| `act_for_others` | **대행** — 「누구를 위해」 를 밝히고 그 사람 이름으로 만든다 |

**사람 세션에는 범위를 걸지 않는다** — 그 사람의 권한이 이미 한계다. 범위는 기계 자격에만
거는 울타리다. `act_for_others` 는 **남의 이름을 빌리는 일**이라 아무 토큰에나 주지 않는다.

## 2. 약속

**오류는 한 모양이다.** `code` 는 안 바뀐다 — 기계는 문구가 아니라 그것으로 가른다.

```json
{"error": {"code": "CCR-AUTH-0100", "message": "로그인이 필요합니다.",
           "request_id": "398a92f14484", "details": {}}}
```

`request_id` 는 응답 헤더에도 있다. 로그에 물어볼 때 이것 하나면 된다.

**목록은 한 모양이다.**

```json
{"items": [...], "total": 128, "limit": 20, "offset": 0}
```

**단위**: 치수는 mm, 각도는 도(°). 물성 `payload` 만 예외로 **MatNexus 의 단위를 그대로**
쓴다 — 우리가 값을 해석하지 않기 때문이다(「어느 것이 영률인가」 는 솔버를 아는 쪽의 일).

## 3. 오케스트레이터 한 바퀴

기계가 지휘하는 그림이 이 API 의 주된 쓰임이다. **아래는 실제로 돌려 본 결과다**(2026-09-24).

### ① 만들고 · 기다리고 · 내보낸다 — 한 번에

```bash
curl -X POST "http://<호스트>/api/doe/run" \
  -H "Authorization: Bearer <PAT>" -H "Content-Type: application/json" -d '{
    "name": "브래킷 압력 훑기",
    "recipe": {"params": {"두께": 6.0, "압력": 2.0},
               "nodes": [{"id": "판", "op": "box", "length": 90, "width": 60,
                          "height": "=두께", "align": ["center","center","min"]}]},
    "conditions": {
      "named_selections": [{"name": "윗면", "entity": "face", "select": {"role": "top"}}],
      "loads": [{"name": "누름", "type": "pressure", "on": "윗면", "magnitude": "=압력"}]},
    "factors": [{"name": "압력", "mode": "list", "values": [2, 3]}],
    "idempotency_key": "orch-2026-09-24-001",
    "on_behalf_of": "designer@example.local"
  }'
```

답에서 볼 것:

```
소유자 김설계 · 돌린 쪽 오케스트레이터
점 2 · 성공 2 · 폴더 /srv/share/브래킷_압력_훑기-98e481ec
점이 쓰는 STEP: ["shapes/d93590863084.step"]
```

- **`on_behalf_of` 를 꼭 준다.** 안 주면 소유자가 서비스 계정이 되고, 정작 사람이 제 활동에서
  못 찾는다. 주면 소유자는 그 사람, 「누가 돌렸나」 는 따로 남는다.
- **`idempotency_key` 를 꼭 준다.** 이 호출은 오래 기다리므로 중간에 끊길 수 있고, 그때 다시
  부르는 것이 정상이다. 열쇠가 같으면 **이미 만든 것을 돌려준다**(201 이 아니라 **200**).
  같은 열쇠에 다른 요청이면 400 으로 거절한다.
- **안 끝나도 답은 온다.** `wait_seconds`(기본 300)가 다 되면 그때 상태로 돌아오고, 그 경우
  **보내지 않는다** — 만들다 만 폴더를 해석이 읽으면 안 된다. 이어서 `POST /doe/{id}/wait`.
- `export=false` 로 만들기만 할 수 있다(조건만 바꿔 가며 쌓아 둘 때).

### ② 진행만 묻는다

```bash
curl -H "Authorization: Bearer <PAT>" http://<호스트>/api/doe/<id>/status
# {"status": "done", "done": 2, "failed": 0, "files_ready": true, "folder": "…"}
```

**설계점 표는 안 준다.** 「끝났나」 를 보려고 200줄을 되풀이해 받지 않게 따로 둔 자리다.
표가 필요하면 `GET /doe/{id}`, 표만 CSV 로 받으려면 `GET /doe/{id}/manifest.csv`.

기다려 주는 자리는 `POST /doe/{id}/wait?seconds=30`(한 번에 최대 120초). **끝을 보장하지
않는다** — 더 오래 물면 프록시가 먼저 끊고, 그때 기계는 「실패」 와 「아직」 을 구별하지
못한다. `waited_out` 이 참이면 다시 부르면 된다. **1초마다 `status` 를 두드리지 마라.**

### ③ 해석을 걸고, 다 읽었으면 알린다

폴더 경로를 SimEngBay 에 넘긴다(그쪽 일). 다 읽었으면:

```bash
curl -X POST -H "Authorization: Bearer <PAT>" http://<호스트>/api/doe/<id>/release
```

「성공했다」 가 아니라 **「더 안 읽는다」** 는 뜻이다. 실패해서 다시 돌릴 생각이면 부르지
마라 — 알린 폴더는 보관 기한을 기다리지 않고 치워진다. 남겨야 하면
`POST /doe/{id}/keep?keep=true`(영구보관, 두 폴더 모두에 걸린다).

**대행으로 만든 기계는 제가 만든 것을 제가 몰 수 있다** — 소유자는 사람이지만 돌리고 ·
보내고 · 알리는 것은 기계다.

### ④ 파일이 치워졌으면 다시 만든다

```bash
curl -H "Authorization: Bearer <PAT>" http://<호스트>/api/doe/<id>/status
# {"files_ready": false, …}   ← 보관 기한이 지나 치워졌다
curl -X POST -H "Authorization: Bearer <PAT>" "http://<호스트>/api/doe/<id>/rerun?only=all"
```

스냅샷(레시피 · 인자 · 시드 · 조건)이 DB 에 남으므로 **같은 것이 그대로** 다시 난다.
`only=failed` 면 실패한 점만(파일이 사라진 점은 `ok` 였어도 다시 만든다).

## 4. 폴더 — 우리가 넘기는 것

```
브래킷_압력_훑기-98e481ec/
  README.txt       사람이 열어 볼 한 장
  manifest.csv     설계점마다 바꾼 변수 값 · 파일 이름 · 상태
  study.json       레시피 스냅샷 · 인자 · 시드 · **만든 사람과 돌린 쪽**
  conditions.json  조건 한 벌 — 식이 있는 그대로(사람이 읽는 정본)
  points/p0001.json   이 점의 모든 것 — 변수 값 · 영역과 바디의 좌표 지문 ·
                      그 값으로 **풀린** 조건 · 이 점이 쓰는 `step_file`
  shapes/<지문>.step  **여러 점이 나눠 쓰는 형상.** 조건만 훑으면 형상이 전부 같으므로
                      한 벌만 둔다. 이 폴더가 없으면 점마다 형상이 다른 것이다
                      (그때는 `points/pNNNN.step`)
```

**파일 이름을 짐작하지 마라** — 어느 점이 어느 STEP 을 쓰는지는 표와 점 파일의 `step_file`
이 말한다. 같은 STEP 을 가리키는 점들은 메시도 한 번만 만들면 된다.

**해석 결과는 이 폴더로 돌아오지 않는다.** 이 플랫폼은 CAD 를 DOE 로 만드는 데 특화하고,
결과 화면과 설계점 고르기는 해석 플랫폼이 한다(`해석-조건-설계.md` 0장).

## 5. 이 API 의 나머지

`/api/docs` 가 묶음마다 무엇을 하는 곳인지 말한다. 큰 줄기만:

| 묶음 | 무엇 |
| --- | --- |
| `auth` | 로그인 · PAT 발급 · 범위 목록(`GET /auth/token-scopes`) |
| `works` | **내 작업** — 비공개로 그리는 자리. 버전마다 레시피와 해석 조건 |
| `parts` · `jigs` · `templates` | 승격된 공용 카탈로그(불변 버전) |
| `cad` | 레시피 검증 · 평가 · 질의 · 셀렉터 후보 · 조건 사양표. **대부분 아무것도 저장하지 않는다** |
| `doe` | 위 3장 |
| `materials` | 물성 — MatNexus 중계, 못 닿으면 올려 둔 카탈로그(`fallback`) |
| `jobs` | 작업 큐 |
| `accounts` · `server` | 관리자용 |
| `system` | `GET /health` — 살아 있나 · 버전 |

## 6. 아직 없는 것

- **웹훅.** 지금은 부르는 쪽이 `status` 나 `wait` 로 묻는다. 기계가 늘어나면 그때.
- **버전 붙은 경로**(`/api/v1/…`). 지금은 경로 하나이고, 바꿀 때는 `code` 와 응답 모양을
  유지한다. 깨는 변경이 필요해지면 그때 나눈다.
