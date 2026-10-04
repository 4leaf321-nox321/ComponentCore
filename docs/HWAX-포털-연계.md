# HWAX 포털 연계

CompCore 를 HWAX 포털에 붙이는 방법을 정리한다. 포털에 붙은 다른 앱(ReportArchive 등)과 **같은
계약**을 쓰므로 포털 쪽은 설정 몇 줄이면 되고, CompCore 만을 위한 포털 코드는 없다.

| | 하는 일 | CompCore 쪽 |
| --- | --- | --- |
| ① 화면 SSO | 포털 타일 · 링크로 들어오면 포털 계정으로 로그인된다 | `/api/auth/portal-callback` · `/api/auth/portal-exchange` |
| ② MCP 위임 | 포털 채팅(게이트웨이)이 **그 사람의 토큰**으로 MCP 를 부른다 | `/api/auth/sso` · `/sso/verify` · `/sso/revoke` |
| ③ 화면 링크 | MCP 도구의 답에 「화면에서 열기」 주소(`url`)가 붙는다 | `/api/health` 의 `public_url` |
| ④ 사람 찾기 | LoginId → 이메일(대소문자 무시) → 없으면 계정 생성 | ①②가 같은 규칙을 쓴다 |

**설정이 비면 모두 꺼진다.** 창구는 404 이고 로그인 화면에 포털 단추도 없다. 단독 설치는 그대로
쓴다.

## 1. 포털 쪽 설정

| 위치 | 값 |
| --- | --- |
| 포털 라우트(`routes.local.env`) | `compcore=http://<CompCore 서버>:8060/` — 끝의 `/` 로 접두어를 벗긴다 |
| 포털 타일(`systems.yaml`) | `integration_type: jwt-handoff` · `audience: compcore` · `url: /compcore/api/auth/portal-callback` |
| MCP 게이트웨이 | 위임 창구 `https://<포털>/compcore/api/auth/sso`(또는 서버 직통) · 공유 비밀 = CompCore 의 `HEAX_SSO_SECRET` · MCP 주소 `http://<CompCore 서버>:8062/mcp` |

포털은 `X-Forwarded-Prefix: /compcore` · `X-Forwarded-Proto` · `X-Forwarded-For` 를 붙여 넘긴다.
CompCore 는 `TRUST_PROXY=true` 일 때 이 헤더를 읽어 화면 자산 · 쿠키 · 이동 주소를 접두어 아래로
맞춘다. 접두어는 **요청마다** 읽으므로, 같은 설치를 IP:포트로 바로 열어도 화면이 뜬다.

## 2. CompCore 쪽 설정(`.env`)

| 키 | 예 | 비우면 |
| --- | --- | --- |
| `TRUST_PROXY` | `true` | 접두어 · 원래 IP 를 모른다 |
| `FORWARDED_ALLOW_IPS` | 포털 박스 IP | `TRUST_PROXY` 일 때 모든 곳의 `X-Forwarded-*` 를 믿는다 |
| `APP_PUBLIC_URL` | `https://<포털>/compcore` | MCP 답에 화면 링크가 붙지 않는다 |
| `PORTAL_JWKS_URL` | `http://<포털>:8088/.well-known/jwks.json` | ① 화면 SSO 꺼짐 |
| `PORTAL_ISSUER` | `https://<포털>` | 발급자를 확인하지 않는다 |
| `PORTAL_AUDIENCE` · `PORTAL_SYSTEM_ID` | `compcore` | `APP_SLUG` |
| `PORTAL_JIT_CREATE` | `true` | (기본 `true`) `false` 면 관리자가 만든 사람만 들어온다 |
| `HEAX_SSO_SECRET` | `openssl rand -hex 32` | ② 위임 창구 꺼짐 |
| `HEAX_SSO_ALLOWED_IPS` | 포털 박스 IP | IP 를 보지 않는다(비밀만 본다) |
| `HEAX_SSO_JIT_CREATE` | `true` | (기본 `true`) |

`FORWARDED_ALLOW_IPS` 를 비워 두면 앱 포트에 바로 닿는 누구나 `X-Forwarded-For` 를 꾸며
`HEAX_SSO_ALLOWED_IPS` 를 넘을 수 있다. 포털 뒤에서는 포털 박스 IP 를 적는다.

## 3. ① 화면 SSO

포털이 launch 토큰(RS256 · 90초 · `kid` · `aud` · `iss` · `scope=launch` · `jti`)을 준다.
CompCore 는 포털 JWKS 로 서명을 확인하고(5분 캐시, 모르는 `kid` 면 다시 받는다), `jti` 를 DB
(`sso_used_jti`)에 넣어 **한 번만** 받는다. 통과하면 비밀번호 로그인과 **같은 세션**(httpOnly
refresh 쿠키 + access 토큰)을 준다.

- **타일 클릭** — 포털 화면이 `token` 을 콜백으로 폼 POST 한다. 콜백은 쿠키를 심고
  `/compcore/` 로 보낸다. 토큰을 URL 에 싣지 않는다. 실패하면 `/compcore/login?sso_error=…` 로
  보내 까닭을 보인다.
- **주소로 바로 들어옴**(북마크 · 채팅의 화면 링크) — 포털에 로그인한 브라우저(`hwax_csrf`
  쿠키)라면 화면이 포털의 표준 `POST /systems/compcore/launch` 를 포털 세션으로 불러 토큰을 받고
  `/api/auth/portal-exchange` 로 바꾼다. 로그인 화면에는 「HWAX 포털 계정으로 계속」 단추가 뜬다.
- **로그아웃** — CompCore 에서 로그아웃하면 그 브라우저 세션 동안은 자동으로 다시 들이지 않는다.
  포털에서 로그아웃해도 CompCore 세션은 그 만료까지 남는다(다른 jwt-handoff 앱과 같다).
- **임시 비밀번호 계정** — 관리자가 만든 계정(첫 로그인 때 비밀번호 변경)에 포털로 처음 오면,
  임시 비밀번호를 없애고 변경 강제를 푼다. 포털로 오는 사람은 임시 비밀번호를 모를 수 있어 변경
  화면에 갇히기 때문이다. 비밀번호로도 들어오려면 관리자가 비밀번호를 초기화한다.

## 4. ② MCP 위임 창구

포털 게이트웨이는 브라우저 없이 서버끼리 부른다. 공유 비밀과 포털이 확인한 이메일로 **그 사람
이름의 개인 토큰**을 받고, 그 토큰으로 MCP 를 부른다. CompCore 는 그 사람의 권한으로 처리한다.
공유 비밀은 이 창구에서만 통하며, 일반 API 는 「사용자 헤더」 를 믿지 않는다.

```
POST /api/auth/sso
  X-Heax-Gateway-Secret: <HEAX_SSO_SECRET>
  X-Heax-User-Email:     kim@example.com
  X-Heax-User-Name:      %ED%99%8D%EA%B8%B8%EB%8F%99     (퍼센트 인코딩, 처음 만들 때 표시 이름)
  X-Heax-Client:         mcp                              (client 마다 토큰 하나)

200 {"success": true, "data": {"access_token": "compcore_pat_…", "token_type": "bearer",
                               "expires_in": 172800, "needs_workspace": false}}
```

| 상황 | 답 |
| --- | --- |
| `HEAX_SSO_SECRET` 이 비었다 | 404(창구 없음) |
| 허용 IP 밖 | 403 |
| 비밀 불일치(상수 시간 비교) | 401 |
| 이메일 없음 · 형식 아님 | 400 · 401 |
| 정지 · 삭제된 계정, 자동 생성 꺼짐 | 403(404 는 「창구 꺼짐」 으로 예약) |
| 같은 사람 · 같은 client 로 다시 받음 | 직전 토큰을 지우고 새로 준다 |

`POST /api/auth/sso/verify` 는 비밀만 확인한다(204). `POST /api/auth/sso/revoke` 는 그 사람 · 그
client 의 토큰을 지운다(`{"ok": true, "revoked": n}`).

**위임 토큰의 울타리** — 토큰은 2일짜리이고 범위는 `read` · `write` · `portal` 이다. `portal`
범위가 있으면:

- 관리자 기능(계정 · 서버 설정 · 작업 점검 등)은 403 이다. 관리자인 사람의 토큰이라도 그 요청
  에서는 일반 사용자로 본다 — 남의 작업을 관리자 권한으로 열지 못한다. DB 의 관리자 표시는
  그대로다.
- 계정 설정(토큰 발급 · 비밀번호 · 프로필)은 바꾸지 못한다. 토큰을 새로 만들 수 있으면
  `portal` 없는 토큰으로 울타리를 넘기 때문이다.
- 사람은 「내 정보 → 개인 토큰」 에서 `HWAX 포털 게이트웨이 (mcp)` 를 보고 직접 폐기할 수 있다.

채팅으로 계정 · 서버 설정을 바꿀 일은 없다고 본다. 관리자 작업은 화면에서 한다.

## 5. ③ 화면 링크

MCP 도구(`create_work` · `get_work` · `save_version` · `restore_version` · `duplicate_work` ·
`copy_part_to_work` · `doe_create` · `doe_run` · `doe_status` · `doe_wait` · `doe_clone` · `get_part` · `get_jig` ·
`promote_part` · `promote_jig_recipe`)의 답에 `url` 이 붙는다(예:
`https://<포털>/compcore/works/<id>`). 주소는 MCP 서버의 `PLATFORM_PUBLIC_URL`, 없으면 백엔드
`/api/health` 의 `public_url`(= `APP_PUBLIC_URL`)이다. 둘 다 비면 붙이지 않는다. 포털 안에서 이
링크를 누르면 ① 로 바로 로그인되어 열린다.

## 6. ④ 사람 찾기

1. 토큰에 LoginId(`login_id`)가 있으면 그것으로 찾는다.
2. 없으면 이메일로 찾는다(대소문자 무시). 찾으면 LoginId 를 새긴다. 메일 주소가 바뀌어도 같은
   사람이 계정 둘이 되지 않는다(LoginId 로 찾았는데 메일이 다르면, 새 주소를 아무도 안 쓸 때
   따라간다).
3. 없으면 계정을 만든다(`PORTAL_JIT_CREATE` · `HEAX_SSO_JIT_CREATE`). 비밀번호는 아무도 모르는
   값이다 — 비밀번호 로그인은 관리자가 초기화한 뒤에 된다.
4. 정지 · 삭제된 계정은 SSO 로도 들어오지 못한다. 퇴사 · 정지는 CompCore 가 판단한다.

## 7. 점검

```bash
# 포털 공개키가 보이나
curl -s http://<포털>:8088/.well-known/jwks.json | head -c 200
# 위임 창구의 비밀이 맞나(204)
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "X-Heax-Gateway-Secret: $HEAX_SSO_SECRET" \
  http://<CompCore 서버>:8060/api/auth/sso/verify
# 화면 주소
curl -s http://<CompCore 서버>:8060/api/health
```

포털 안에서 `https://<포털>/compcore/works` 를 바로 열어 로그인 화면 없이 뜨는지 보고, 새로
고쳐도 로그인이 유지되는지 본다(쿠키 경로가 `/compcore/api/auth` 여야 한다).
