"""설정 — 환경변수(.env) -> 기본값.

os.getenv 가 코드에 흩어지면 값 하나를 바꾸는 데 재배포가 필요해진다. 읽는 지점은
`get_settings()` 하나다.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.branding import DEFAULT_APP_NAME, DEFAULT_APP_SLUG, DEFAULT_APP_TAGLINE

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    # utf-8-sig 로 읽는다. BOM 이 붙은 .env 는 **첫 줄 키만 조용히 무시된다** —
    # 그 키가 기본값으로 떨어지므로, 운영이 development 로 떠서 reload 가 켜진 채 돈다.
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8-sig", extra="ignore"
    )

    app_env: str = "development"
    """development | production. 기동 방식과 로그 수준을 가른다."""

    app_slug: str = DEFAULT_APP_SLUG
    """기계가 읽는 이름 — DB 이름 · 리프레시 쿠키 이름이 여기서 나온다. 설치 뒤에는 바꾸지
    않는다 — 바꾸면 쿠키가 무효가 되고 DB 이름이 어긋난다."""
    app_name: str = DEFAULT_APP_NAME
    """화면 제목 · API 문서 제목 · 기동 로그 · `/api/health` 의 `app`."""
    app_tagline: str = DEFAULT_APP_TAGLINE

    database_url: str = ""
    """비우면 `postgresql+psycopg://postgres:postgres@localhost:5432/<app_slug>`.
    시험은 이 이름에서 `_test` 를 파생해 쓴다(tests/conftest.py)."""

    host: str = "0.0.0.0"
    port: int = 8060
    """**플랫폼마다 10씩 벌린다** — MatNexus 8010, TestScope 8020, CrossAXTF 8030,
    StandardPlatform 8040, (예약) PartTrace 8050, 이 플랫폼 8060. 개발 백엔드는 +1(8061)을
    쓴다(run.py). 정본 표는 StandardPlatform/docs/새-플랫폼-만들기.md 3.6 — 새 플랫폼은 거기
    한 줄을 더한다."""
    trust_proxy: bool = False
    """앞에 리버스 프록시(nginx)가 있어 `X-Forwarded-*` 를 믿는다. 없으면 끈다."""

    uvicorn_workers: int = 2
    """운영에서 띄울 워커 수. **개발(reload)에서는 무시된다.** 지그 생성은 CPU 를 쓰는
    동기 작업이라 워커 수가 곧 동시에 돌 수 있는 생성 수다."""

    log_dir: Path = BACKEND_DIR / "logs"
    log_retention_days: int = 30

    filestore_dir: Path = BACKEND_DIR / "filestore"
    """올린 제품 STEP 과 생성한 지그(STEP · glTF)가 사는 곳. DB 에는 경로만 둔다.
    운영에서는 bind-mount 된 경로여야 한다 — 이미지 루트는 읽기 전용이다."""

    frontend_dist: Path = REPO_DIR / "frontend" / "dist"
    """존재하면 API 와 같은 프로세스가 SPA 를 서빙한다. 개발 중에는 없다."""

    jwt_secret: str = "dev-only-insecure-secret-change-me"
    """운영에서는 난수로 바꾼다. app_env=production 이면서 기본값이면 **기동을 거부한다**."""

    access_token_minutes: int = 720  # 12시간
    refresh_token_days: int = 30
    refresh_cookie_name: str = ""
    """비우면 `<app_slug>_refresh`. 쿠키는 포트를 구분하지 않아서 같은 서버의 두 플랫폼이
    같은 이름을 쓰면 한쪽 로그인이 다른 쪽 세션을 덮어쓴다."""
    refresh_cookie_secure: bool = False
    """사내망 http 배포가 기본이라 False. https 로 서비스하면 True."""

    login_delay_after: int = 5
    """같은 계정의 로그인 실패가 이 횟수부터 응답을 늦춘다. **잠그지 않는다.**"""
    login_delay_step_seconds: int = 2
    login_delay_max_seconds: int = 30
    login_failure_window_minutes: int = 15

    jobs_inline: bool = False
    """작업을 워커 없이 **요청 안에서** 돌린다. 시험과 워커를 안 띄우는 작은 설치용. 켜면 지그
    생성 요청이 끝날 때까지 응답이 안 온다 — 큰 제품이면 그 시간이 곧 타임아웃이다."""

    mcp_public_url: str = ""
    """AI 도구가 붙는 MCP 주소(예: http://jig.example.com:8062/mcp). 비우면 화면이 접속한
    호스트 + (백엔드 포트 + 2) 로 만든다 — 개발 PC 에서는 그것이 맞고, 프록시 뒤에서는 이 값을
    준다."""

    doe_max_points: int = 200
    """실험계획 한 번에 만드는 설계점 상한. 점마다 형상을 평가하고 STEP 을 쓰므로(수백 ms ~
    수 초) 상한이 없으면 한 요청이 서버를 오래 잡는다. 더 큰 표가 필요하면 .env 에서 올리거나,
    LHS 로 표본 수를 정해 격자 곱을 피한다."""

    doe_gallery_max: int = 24
    """실험계획 형상 보기에서 **한 번에 그리는** 형상 수(겹쳐 보기 · 나란히). 넘으면 쪽으로
    나눠 넘긴다. 브라우저가 그리는 양이라 크게 잡으면 느려진다 — 관리자가 화면에서 바꾼다."""

    list_page_size: int = 20
    """목록 한 쪽에 보이는 줄 수(실험계획 · 내 작업 · 부품 · 지그 · 템플릿 · 실행 기록)."""

    doe_workers: int = 0
    """설계점 형상을 **몇 프로세스로 나눠** 만드나. 0 이면 코어 수에 맞춘다(하나는 웹 · DB
    몫으로 남기고 넷까지). 형상 만들기가 거의 전부라 점이 많으면 그만큼 빨라지고, 메모리는
    프로세스마다 build123d 한 벌(수백 MB)이 든다 — 작은 서버면 1~2 로 둔다."""

    mesh_suggestion_max_nodes: int = 100_000
    """설계점 파일의 **전역 요소 크기 제안**이 넘지 않을 절점 수(추정). 넘으면 크기를
    키운다 — 보드굽힘에 0.6 mm 를 제안했더니 CalculiX 가 감당 못 할 크기였다(1 mm 에서 25만
    절점 · 30분 넘음, 운영에서 메모리가 바닥난 적도 있다). 해석 서버의 메모리에 맞춘다. 0 이면
    걸지 않는다."""

    doe_max_samples: int = 500
    """LHS 표본 수 상한의 .env 기본값. 설계점 상한이 먼저 걸리므로 그보다 크게 둘 뜻은 없다."""

    doe_export_root: Path = Path("/mnt/f/data/0_Program/73_CompCore")
    r"""실험계획(DOE)이 STEP · manifest 를 쏟아 놓는 **공유 폴더**. 해석(ANSYS)을 도는 쪽이 이
    폴더를 그대로 읽는다. 서버가 WSL 이면 `/mnt/f/...`, 화면에는 `F:\...` 로 보여 준다.
    폴더가 없거나 못 쓰면 DOE 를 만들 때 그 사실을 말한다 — 조용히 로컬에 쓰지 않는다."""

    doe_export_ttl_days: int = 30
    """공유 폴더의 스터디 폴더를 **며칠 두나**. 0 이면 자동 삭제를 안 한다.

    공유 폴더는 보관소가 아니라 **전달 큐**다 — 정본은 서버 보관 폴더와 DB 이고, 「보내기」 를
    다시 누르면 같은 폴더가 다시 선다(`docs/오케스트레이션-연계-설계.md`). 수명이 없으면
    오케스트레이터가 하루 수십 번 돌리는 날 폴더가 영원히 쌓인다.

    **영구보관은 스터디마다 켠다**(`DoeStudy.keep_forever`) — 기한은 기본값이고 예외가 규칙보다
    강하다."""

    doe_local_ttl_days: int = 180
    """**서버 보관 폴더**(filestore/doe/…)의 스터디 폴더를 며칠 두나. 0 이면 안 지운다.

    공유 폴더(30일)보다 훨씬 길다 — 여기는 전달 큐가 아니라 보관소이고, 「보내기」 의 복사원도
    여기다. 그래도 무한은 아니다: 파일은 다시 만들 수 있고(`rerun_study` 가 스냅샷으로
    되살린다) 스터디 줄과 이력은 지우지 않으니, 잃는 것은 **다시 만드는 시간뿐**이다.

    영구보관(`DoeStudy.keep_forever`)은 두 폴더에 똑같이 걸린다 — 「이건 남겨야 한다」 는 한 번
    켜면 끝이어야지, 폴더마다 따로 켜게 하면 한쪽만 켜 둔 날 나머지가 사라진다."""

    matnexus_base_url: str = ""
    """물성 플랫폼(MatNexus) 의 주소 — 예 `http://10.252.39.120:8010`. **비우면 물성 탐색기가
    꺼진다**(올려 둔 카탈로그 파일만 쓴다). 그쪽은 0.0.0.0:8010 에 바인딩하므로 방화벽만
    열리면 다른 호스트에서 닿는다."""

    matnexus_token: str = ""
    """MatNexus 의 개인 토큰(`mnx_pat_…`). **서버가 대신 부르는 자격**이라 사람마다 안 넣는다.

    **그 PAT 에는 범위가 없다**(2026-09-24 재확인 — 토큰을 만들 때 정하는 것은 이름과 만료일
    뿐이다). 그래서 **무엇이 보이나는 전적으로 「이 토큰이 누구냐」 로 정해진다** — 그 계정이
    속한 부서의 재료가 보인다. 시스템 관리자 토큰을 넣으면 전부 보이고, 그것은 MatNexus 가
    부서로 나눠 둔 권한을 이쪽에서 통째로 우회하는 것이다. **읽기만 하는 전용 계정**을
    만들어 필요한 부서에만 넣는 것이 맞다.

    **설정 표가 아니라 `.env` 에 둔다** — 서버 설정은 관리자 화면에 평문으로 보인다."""

    matnexus_workspace: str = ""
    """물성 탐색기가 볼 **부서**(MatNexus 의 workspace slug — 예 `default` · `polymer`).

    비우면 그 토큰의 계정이 보는 전부다. 채우면 그 부서 것만 묻는다(`?workspace=<slug>`).

    **이것은 권한이 아니라 좁히기다.** 토큰이 볼 수 있는 것보다 넓게 만들 수는 없다 — 권한은
    MatNexus 가 정하고 우리는 그 안에서 고를 뿐이다. 부서가 여럿인 계정으로 붙었는데 물성
    탐색기에 남의 부서 재료까지 쏟아질 때 쓴다.

    예전에는 `scope=global` 을 우리가 박았다. **그 칸은 2026-09-24 권한 개편으로 없어졌고**,
    MatNexus 는 모르는 질의를 조용히 무시하므로 그 뒤로는 **아무 필터도 아니었다**(실측).
    이름이 살아 있는 척하는 코드가 제일 나쁘다 — 그래서 지웠다."""

    max_upload_mb: int = 200
    """제품 STEP 상한. 조립체 STEP 은 수백 MB 가 되기도 하지만, 그것은 먼저 부품으로 쪼개서
    올리는 것이 맞다 — 지그는 부품 단위로 잡는다."""

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5230", "http://127.0.0.1:5230"]
    )
    """개발 서버(Vite)용. 배포에서는 동일 출처라 필요 없다."""

    # ── HWAX 포털 연계 — **비어 있으면 꺼진다**(단독 설치는 아무것도 열지 않는다) ──────
    forwarded_allow_ips: str = ""
    """`X-Forwarded-*` 를 믿을 프록시 IP(쉼표로). 비우면 `trust_proxy` 일 때 모두를 믿는다(예전
    동작). 포털 뒤에서는 **포털 박스 IP** 를 준다 — 그래야 아무나 `X-Forwarded-For` 를 꾸며
    위임 창구의 IP 제한을 넘지 못한다."""
    app_public_url: str = ""
    """사람이 여는 이 플랫폼의 주소(예: https://hwax.sec.samsung.net/compcore). MCP 도구가 답에
    화면 링크를 붙일 때 쓴다. 비우면 링크를 안 붙인다."""
    portal_jwks_url: str = ""
    """포털 SSO(jwt-handoff)의 공개키 주소(예: http://<포털>:8088/.well-known/jwks.json).
    **비우면 포털 로그인이 꺼진다**(`/api/auth/portal-*` 가 404)."""
    portal_audience: str = ""
    """포털 타일의 audience — 비우면 `app_slug`."""
    portal_issuer: str = ""
    """포털 토큰의 발급자(예: https://hwax.sec.samsung.net). 비우면 발급자를 보지 않는다."""
    portal_system_id: str = ""
    """포털의 타일 id — 화면이 포털 세션으로 launch 토큰을 받는 주소(`/systems/{id}/launch`).
    비우면 `app_slug`."""
    portal_jit_create: bool = True
    """포털 SSO 로 처음 온 사람의 계정을 만든다(2026-10-04 결정 — ReportArchive 와 같다). 끄면
    관리자가 미리 만든 사람만 들어온다."""
    heax_sso_secret: str = ""
    """포털 MCP 게이트웨이의 **사용자 위임 창구**(`/api/auth/sso`) 공유 비밀 — 포털 표준(ste
    방식). **비우면 창구가 없다**(404). `openssl rand -hex 32`."""
    heax_sso_allowed_ips: str = ""
    """위임 창구를 부를 수 있는 IP(쉼표로) — 포털 박스. 비우면 IP 를 보지 않는다(비밀만)."""
    heax_sso_jit_create: bool = True
    """위임 창구에서도 모르는 이메일이면 계정을 만든다(포털 SSO 와 같은 규칙)."""

    # --- StandardPlatform 에서 들인 온톨로지 · 데이터 작업 · 지표의 설정(ADR 0008) ---------

    filestore_gc_hours: int = 24
    """첨부 저장소(`filestore/blobs`)의 **고아 파일 정리**를 워커가 몇 시간마다 하나
    (`files/gc.py`). 0 이면 안 한다 — 시스템 관리자가 작업(「고아 첨부 파일 정리」)으로만."""

    access_log_retention_days: int = 365
    """접근 로그(`access_logs` — 누가 어느 통로로 무엇을 불렀나)를 며칠치 남기나. 0 이면 지우지
    않는다. 지우는 주기가 없어 쌓이기만 했다(2026-10-10). **감사 기록(변경 이력)은 이것과
    상관없이 지우지 않는다** — 객체 이력과 되돌리기가 거기에 기댄다."""

    core_watermark_floor_seconds: int = 600
    """코어 API 가 주는 `as_of` 는 **아직 안 끝난 적재보다 앞서지 않는다**. 다만 열어 두고 잊은
    트랜잭션 하나가 그 시각을 영영 묶어 두면 받는 쪽은 새 값을 못 본다 — **이만큼 아무것도 안
    한** 트랜잭션은 셈에서 뺀다.

    ⚠️ 재는 것은 「얼마나 오래됐나」 가 **아니라** 「마지막으로 무엇이라도 한 때」 다.
       오래됐나로 자르면 한 시간 도는 백필이 빠지고, 그 사이에 받아 간 쪽은 그 백필분을
       영영 잃는다(그 구멍을 막은 것이 이 칸이다)."""

    datasource_dir: Path | None = None
    """데이터 소스가 **파일**(CSV·Excel·JSON)을 읽어도 되는 폴더. 비우면 URL 로만 읽는다.

    아무 경로나 읽게 두면 데이터 소스 화면이 서버의 모든 파일을 읽는 문이 된다 — 그래서
    이 폴더 아래만. 운영에서는 bind-mount 된 곳(예: `/data/filestore/incoming`)을 적고,
    바깥 시스템이 거기로 파일을 떨어뜨리게 한다."""

    job_file_inline_max_bytes: int = 32 * 1024 * 1024
    """작업 파일을 **DB 에 담는** 상한 — 넘으면 공용 저장소의 작업 폴더
    (`FILESTORE_DIR/_jobs/`)에 두고 행에는 경로만 둔다(`jobs/files.py`, 2026-10-10).

    작은 것은 DB(`job_files.data`)가 낫다 — 서버 두 대가 함께 읽고, 공용 폴더는 다른 사업장이라
    느리다(`docs/작업-워커-설계.md` 3장). 큰 것은 DB 가 못 견딘다: bytea 한 값은 1GB 까지이고,
    올린 2GB 가 그대로 WAL · 복제로 대기 서버까지 흐르며, 읽으려면 통째로 메모리에 올려야 한다.
    공용 폴더는 첨부가 이미 쓰는 곳이라(두 대가 같은 경로로 마운트) 어느 워커가 집어도 읽는다.
    작업 결과 파일(내보내기)도 같은 문턱을 따른다."""

    job_file_max_bytes: int = 100 * 1024 * 1024
    """**표 파일**(일괄 입력 · 묶음)의 작업 파일 상한 — 종류가 따로 정하지 않으면 이것이다
    (`kinds.Kind.max_file_setting`). 처리가 파일을 통째로 메모리에 올려 풀므로 상한이 있어야
    한다."""

    job_photos_max_bytes: int = 2 * 1024 * 1024 * 1024
    """**사진 zip**(사진 일괄 업로드)의 상한 — 2GB. zip 은 받을 때도(흘려 받기) 처리할 때도
    (파일로 열어 한 장씩) 통째로 메모리에 올리지 않으므로 표 파일(`job_file_max_bytes`)과
    상한이 다르다."""

    job_file_ttl_days: int = 7
    """작업 파일을 지우기까지. 임시물이 영구물이 되면 표가 DB 의 대부분이 된다."""

    job_max_rows: int = 100_000
    """작업 경로의 행 상한. 요청 경로의 5,000(`bulk.MAX_ROWS`)은 요청 시간 때문이었다 —
    워커에서는 트랜잭션 하나가 감당하는 크기만 남는다."""

    job_notify_after_seconds: int = 20
    """이보다 오래 걸린 작업만 끝났을 때 알린다. 짧게 끝난 것은 사람이 그 화면에서 봤다 —
    본 것을 한 번 더 말하면 그 종은 잡음이 되고, 잡음이 된 종은 진짜 하나가 울려도 안
    읽힌다."""

    job_output_max_bytes: int = 512 * 1024 * 1024
    """작업이 **만드는** 결과 파일의 상한 — 올리는 파일(`job_file_max_bytes`)과 따로 둔다.
    기록 200만 건 내보내기는 zip 으로도 128MB 였다(실측). 큰 결과는 공용 저장소의 작업 폴더에
    놓이지만(`job_file_inline_max_bytes`) 만드는 동안 메모리에 다 들고 있으므로 이 상한은
    그대로 둔다 — 넘으면 조건으로 좁혀 나눠 내보내라고 말한다."""

    job_ttl_days: int = 30
    """**끝난** 작업 기록을 지우기까지. 타이머가 소스마다 5분에 한 줄을 넣으므로 하루 288행이
    쌓인다 — 안 지우면 사람이 올린 작업이 그 사이에 파묻혀 「작업」 화면이 못 쓰게 된다.
    도는 것(`queued`·`running`)은 아무리 오래돼도 안 지운다."""

    metrics_night_hour: int = 2
    """하루 이상 주기의 지표를 세는 **밤 시간**(서버 현지 시각, 0 ~ 23). 타이머
    (`scripts/recompute_metrics.py --due`)는 매시간 깨고, 「매일 밤 · N일마다 밤」 지표는 이
    시간에만 센다(`metrics/services.due`)."""

    metrics_full_every_days: int = 7
    """**전량으로 다시 세는 주기**(일). 그 사이 타이머 · 적재 뒤의 계산은 바뀐 기간만 센다
    (`metrics/incremental.py`). 증분이 못 보는 변경(감사 없이 바뀐 기록 · 타입 옮김 등)을 이
    주기로 바로잡는다. 0 이면 늘 전량."""

    metrics_incremental_max_share: float = 0.2
    """바뀐 원천 기록이 원천의 이 비율을 넘으면 전량으로 센다 — 그러면 전량이 오히려 싸다."""

    metrics_max_cells: int = 10_000_000
    """지표 하나의 셀 상한 — 계획이 이보다 많이 어림하면 정의를 거절하고, **계산이 실제로
    이보다 많이 세면 그 계산을 실패로 둔다**(옛 값이 남는다, ADR 0013 · 0023). 셀은 기록보다
    훨씬 적어야 미리 세는 뜻이 있다. 자유 글자 기준 하나가 이것을 넘긴다. 셀 하나는 색인까지
    약 400바이트 — 1,000만이면 지표 하나에 4GB(다시 세는 동안 두 벌)."""

    metrics_max_frame_cells: int = 200_000
    """분석 하나가 셀 위에서 계산하려고 **받는** 셀 상한 — 넘으면 거절한다(잘린 셀 위의 통계는
    틀린다, ADR 0014 · 0023). 셀 하나가 Python 에서 약 400바이트 — 20만이면 80MB · 1.4초
    (실측)."""

    metrics_max_read_cells: int = 20_000
    """화면 · MCP 의 읽기(표 · 추이 · 코호트) 한 번이 **돌려주는** 셀 상한 — 넘으면 `truncated`
    로 말한다. 응답 크기라 작게 둔다(셀 하나가 JSON 으로 약 400바이트)."""

    metrics_work_mem: str = "256MB"
    """지표 계산 트랜잭션의 `work_mem`. 200만 건을 묶을 때 기본값(4MB)이면 디스크로 넘어가
    열 배 느리다. 계산은 한 번에 하나만 돌므로(지표마다 자문 잠금) 넉넉히 준다."""

    tombstone_ttl_days: int = 90
    """**끊긴 선의 무덤**을 이만큼만 들고 있는다. 무덤은 영영 쌓이고, 내보내기는 그 이력을
    통째로 보낸다 — 몇 해가 지나면 「지금 무엇이 있나」 보다 「무엇이 없어졌나」 가 더 커진다.
    받는 쪽이 이 기간보다 오래 잠들어 있었다면 처음부터 다시 받아야 한다(그때는 무덤이
    아니라 전량이 정본이다)."""

    undo_journal_ttl_days: int = 30
    """**묶음 한 판을 되돌릴 기록**을 이만큼만 들고 있는다. 바뀐 줄마다 한 줄이라 백필 한
    번이 수만 줄을 남긴다 — 영영 두면 그 표가 데이터보다 커진다. 기간이 지난 판은 목록에
    남지만 「되돌릴 수 없음」 으로 뜬다: 지운 뒤에 되돌리기를 내밀면 눌러 본 뒤에야 안 되는
    것을 안다."""

    worker_max_attempts: int = 3

    worker_stale_seconds: int = 300
    """`running` 인데 이만큼 심장박동이 없으면 워커가 죽은 것으로 보고 되돌린다."""

    public_path: str = ""
    """브라우저가 보는 **주소 접두어** — 여러 플랫폼이 한 호스트명에 경로로 붙을 때
    (`https://hwax.sec.samsung.net/<slug>/` 이면 `/<slug>`). 비우면 루트(`/`).

    앞의 nginx 가 접두어를 **떼고** 앱에 넘긴다(`location /<slug>/ { proxy_pass http://…/; }`).
    앱은 여전히 `/api` · `/assets` 로 받지만, 화면이 부를 주소 · 리프레시 쿠키의 path ·
    문서(`/api/docs`)의 주소는 접두어를 알아야 한다 — `index.html` 에 심어 준다(main.py).
    앞뒤 슬래시는 정리한다: `plm/` → `/plm`."""

    @property
    def base_path(self) -> str:
        """정리된 접두어 — `""` 또는 `/<slug>`."""
        cleaned = self.public_path.strip().strip("/")
        return f"/{cleaned}" if cleaned else ""

    @model_validator(mode="after")
    def _derive_from_slug(self) -> Settings:
        if not re.fullmatch(r"[a-z][a-z0-9]{0,31}", self.app_slug):
            raise ValueError(
                f"APP_SLUG는 영문 소문자로 시작하는 소문자·숫자 32자 이내여야 합니다: "
                f"{self.app_slug!r}"
            )
        if not self.database_url:
            self.database_url = (
                f"postgresql+psycopg://postgres:postgres@localhost:5432/{self.app_slug}"
            )
        if not self.refresh_cookie_name:
            self.refresh_cookie_name = f"{self.app_slug}_refresh"
        if not self.portal_audience:
            self.portal_audience = self.app_slug
        if not self.portal_system_id:
            self.portal_system_id = self.app_slug
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
