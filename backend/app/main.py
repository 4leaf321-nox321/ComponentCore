"""FastAPI 앱 — API 와 SPA 를 한 프로세스가 서빙한다.

**조립은 여기 하나다.** 라우터는 전부 이 파일을 거친다. 모듈이 서로를 import 하지 않게
하려면 조립 지점이 하나여야 하고, 그래야 "이게 왜 안 뜨지" 를 물을 자리가 생긴다.
"""

from __future__ import annotations

import logging
import re
from html import escape as html_escape

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app import handlers, version
from app.config import Settings, get_settings
from app.database import SessionLocal, engine
from app.logging_setup import setup_logging
from app.modules.accounts import routes as accounts_routes
from app.modules.auth import routes as auth_routes
from app.modules.cad import routes as cad_routes
from app.modules.jigs import routes as jigs_routes
from app.modules.jobs import routes as jobs_routes
from app.modules.parts import routes as parts_routes
from app.modules.server import routes as server_routes
from app.modules.templates import routes as templates_routes
from app.modules.works import routes as works_routes
from app.schema_version import warn_if_behind
from app.shared.access_log import AccessLogMiddleware
from app.shared.errors import NotFound, code, register_error_handlers
from app.shared.request_context import RequestIdMiddleware

logger = logging.getLogger(__name__)

API_PREFIX = "/api"


def _api_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix=API_PREFIX)

    @router.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "version": version.current(),
            "app": settings.app_name,
            "slug": settings.app_slug,
        }

    # 모듈 라우터는 **여기서만** 모은다.
    router.include_router(auth_routes.router)
    router.include_router(accounts_routes.router)
    router.include_router(works_routes.router)
    router.include_router(parts_routes.router)
    router.include_router(jigs_routes.router)
    router.include_router(jobs_routes.router)
    router.include_router(cad_routes.router)
    router.include_router(templates_routes.router)
    router.include_router(server_routes.router)
    return router


def _mount_spa(app: FastAPI, settings: Settings) -> None:
    dist = settings.frontend_dist
    index = dist / "index.html"
    if not index.exists():
        logger.info("frontend dist 없음 (%s) — API만 서빙합니다.", dist)
        return

    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    # 이름을 심는다 — 화면은 `<meta name="app-name">` 으로 자기 이름을 안다.
    metas = "\n    ".join(
        f'<meta name="{key}" content="{html_escape(value)}" />'
        for key, value in (
            ("app-name", settings.app_name),
            ("app-slug", settings.app_slug),
            ("app-tagline", settings.app_tagline),
        )
    )
    html = index.read_text(encoding="utf-8").replace("<head>", f"<head>\n    {metas}", 1)
    html = re.sub(
        r"<title>.*?</title>",
        f"<title>{html_escape(settings.app_name)}</title>",
        html,
        count=1,
    )

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    def spa(full_path: str) -> HTMLResponse:
        if full_path.startswith("api/"):
            raise NotFound(
                code("COMMON", 404),
                "존재하지 않는 엔드포인트입니다.",
                details={"path": f"/{full_path}"},
            )
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    logger.info("SPA 서빙: %s", dist)


def _guard_production_secrets(settings: Settings) -> None:
    if settings.app_env != "production":
        return
    if settings.jwt_secret == Settings.model_fields["jwt_secret"].default:
        raise RuntimeError(
            "JWT_SECRET 이 기본값입니다. .env 에 난수 값을 넣고 다시 시작하세요."
        )


def _guard_writable_paths(settings: Settings) -> None:
    """쓸 수 있어야 하는 곳에 쓸 수 있나 — **로그를 열기 전에 본다.**"""
    for label, path in (
        ("LOG_DIR", settings.log_dir),
        ("FILESTORE_DIR", settings.filestore_dir),
    ):
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write-probe"
            probe.touch()
            probe.unlink()
        except OSError as failure:
            raise RuntimeError(
                f"{label} 에 쓸 수 없습니다: {path} ({failure.strerror})"
            ) from failure


def create_app() -> FastAPI:
    settings = get_settings()
    _guard_writable_paths(settings)
    setup_logging(settings)
    _guard_production_secrets(settings)

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=version.current(),
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )

    # 나중에 더한 것이 바깥 — RequestId(바깥) -> AccessLog(안쪽).
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.state.session_factory = SessionLocal
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_error_handlers(app)
    # 작업 종류 — 워커와 같은 함수로 등록한다. 여기서 등록해야 API 가 「모르는 종류」 를 걸 때
    # 거절한다.
    handlers.register_all()
    app.include_router(_api_router(settings))
    _mount_spa(app, settings)  # SPA catch-all 은 반드시 API 라우터 뒤

    warn_if_behind(engine)
    logger.info(
        "%s (%s) 기동 (env=%s)", settings.app_name, settings.app_slug, settings.app_env
    )
    return app


app = create_app()
