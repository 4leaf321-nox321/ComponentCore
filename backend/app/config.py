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

    doe_max_samples: int = 500
    """LHS 표본 수 상한의 .env 기본값. 설계점 상한이 먼저 걸리므로 그보다 크게 둘 뜻은 없다."""

    doe_export_root: Path = Path("/mnt/f/data/0_Program/73_AutoJigGenerator")
    """실험계획(DOE)이 STEP · manifest 를 쏟아 놓는 **공유 폴더**. 해석(ANSYS)을 도는 쪽이 이
    폴더를 그대로 읽는다. 서버가 WSL 이면 `/mnt/f/...`, 화면에는 `F:\...` 로 보여 준다.
    폴더가 없거나 못 쓰면 DOE 를 만들 때 그 사실을 말한다 — 조용히 로컬에 쓰지 않는다."""

    matnexus_base_url: str = ""
    """물성 플랫폼(MatNexus) 의 주소 — 예 `http://10.252.39.120:8010`. **비우면 물성 탐색기가
    꺼진다**(올려 둔 카탈로그 파일만 쓴다). 그쪽은 0.0.0.0:8010 에 바인딩하므로 방화벽만
    열리면 다른 호스트에서 닿는다."""

    matnexus_token: str = ""
    """MatNexus 의 개인 토큰(`mnx_pat_…`). **서버가 대신 부르는 자격**이라 사람마다 넣지
    않는다 — 그리고 그 PAT 에는 범위가 없어서, 우리는 늘 `scope=global`(전역 재료)만 묻는다.
    작업공간 재료까지 보이면 MatNexus 의 권한 구분이 이쪽에서 무너진다(2026-09-24 결정).

    **설정 표가 아니라 `.env` 에 둔다** — 서버 설정은 관리자 화면에 평문으로 보인다."""

    max_upload_mb: int = 200
    """제품 STEP 상한. 조립체 STEP 은 수백 MB 가 되기도 하지만, 그것은 먼저 부품으로 쪼개서
    올리는 것이 맞다 — 지그는 부품 단위로 잡는다."""

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5230", "http://127.0.0.1:5230"]
    )
    """개발 서버(Vite)용. 배포에서는 동일 출처라 필요 없다."""

    @model_validator(mode="after")
    def _derive_from_slug(self) -> Settings:
        if not re.fullmatch(r"[a-z][a-z0-9]{0,31}", self.app_slug):
            raise ValueError(
                f"APP_SLUG 는 소문자·숫자 한 덩어리 32자 이내여야 합니다: {self.app_slug!r}"
            )
        if not self.database_url:
            self.database_url = (
                f"postgresql+psycopg://postgres:postgres@localhost:5432/{self.app_slug}"
            )
        if not self.refresh_cookie_name:
            self.refresh_cookie_name = f"{self.app_slug}_refresh"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
