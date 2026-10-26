"""FastAPI 앱 — API 와 SPA 를 한 프로세스가 서빙한다.

**조립은 여기 하나다.** 라우터는 전부 이 파일을 거친다. 모듈이 서로를 import 하지 않게
하려면 조립 지점이 하나여야 하고, 그래야 "이게 왜 안 뜨지" 를 물을 자리가 생긴다.
"""

from __future__ import annotations

import logging
import re
from html import escape as html_escape
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app import api_docs, handlers, version
from app.config import Settings, get_settings
from app.database import SessionLocal, engine
from app.logging_setup import setup_logging
from app.modules.accounts import routes as accounts_routes
from app.modules.accounts import system as accounts_system
from app.modules.audit import routes as audit_routes
from app.modules.auth import routes as auth_routes
from app.modules.auth import sso as sso_routes
from app.modules.auth.cookies import url_prefix
from app.modules.bundles import routes as bundles_routes
from app.modules.cad import routes as cad_routes
from app.modules.coreapi import routes as coreapi_routes
from app.modules.datasources import routes as datasources_routes
from app.modules.datasources import services as datasources_services
from app.modules.doe import routes as doe_routes
from app.modules.files import routes as files_routes
from app.modules.files import services as files_services
from app.modules.graph import routes as graph_routes
from app.modules.jigs import routes as jigs_routes
from app.modules.jigs import system as jigs_system
from app.modules.jobs import routes as jobs_routes
from app.modules.materials import routes as materials_routes
from app.modules.metrics import routes as metrics_routes
from app.modules.metrics import services as metrics_services
from app.modules.notifications import routes as notifications_routes
from app.modules.objects import attachments as objects_attachments
from app.modules.objects import misses as objects_misses
from app.modules.objects import quality as objects_quality
from app.modules.objects import review as objects_review
from app.modules.objects import routes as objects_routes
from app.modules.objects import services as objects_services
from app.modules.objects import watches as objects_watches
from app.modules.objectsearch import routes as objectsearch_routes
from app.modules.ontology import profile as ontology_profile
from app.modules.ontology import routes as ontology_routes
from app.modules.parts import routes as parts_routes
from app.modules.parts import system as parts_system
from app.modules.rdf import routes as rdf_routes
from app.modules.review import links as review_links
from app.modules.review import registry as review_registry
from app.modules.review import routes as review_routes
from app.modules.search import routes as search_routes
from app.modules.server import routes as server_routes
from app.modules.specimens import routes as specimens_routes
from app.modules.tagging import routes as tagging_routes
from app.modules.tasks import routes as tasks_routes
from app.modules.tasks import services as tasks_services
from app.modules.templates import routes as templates_routes
from app.modules.templates import system as templates_system
from app.modules.voc import routes as voc_routes
from app.modules.webhooks import routes as webhooks_routes
from app.modules.webhooks import services as webhooks_services
from app.modules.works import routes as works_routes
from app.modules.works import system as works_system
from app.modules.workspaces import routes as workspaces_routes
from app.modules.workspaces import services as workspaces_services
from app.schema_version import warn_if_behind
from app.shared import events, extensions, scopes, system_sources
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
            # 사람에게 보여 줄 화면 주소(포털 뒤면 `https://portal/compcore`). MCP 가 결과에
            # 「화면에서 열기」 링크를 붙일 때 읽는다. 비면 링크를 붙이지 않는다.
            "public_url": settings.app_public_url.rstrip("/"),
        }

    # 모듈 라우터는 **여기서만** 모은다.
    router.include_router(auth_routes.router)
    router.include_router(sso_routes.router)
    router.include_router(accounts_routes.router)
    router.include_router(works_routes.router)
    router.include_router(parts_routes.router)
    router.include_router(jigs_routes.router)
    router.include_router(tagging_routes.router)
    router.include_router(jobs_routes.router)
    router.include_router(cad_routes.router)
    router.include_router(templates_routes.router)
    router.include_router(doe_routes.router)
    router.include_router(materials_routes.router)
    router.include_router(search_routes.router)
    router.include_router(server_routes.router)
    router.include_router(specimens_routes.router)
    router.include_router(voc_routes.router)
    # StandardPlatform 에서 들인 것(ADR 0008) — 부서 · 알림 · 첨부 · 감사 · 데이터 작업 ·
    # 온톨로지 ·
    # 객체 · 그래프 · RDF · 찾기 · 지표 · 묶음 · 검토함 · 데이터 소스 · 코어 API · 웹훅.
    router.include_router(workspaces_routes.router)
    router.include_router(notifications_routes.router)
    router.include_router(files_routes.router)
    router.include_router(audit_routes.router)
    router.include_router(tasks_routes.router)
    router.include_router(coreapi_routes.router)
    router.include_router(ontology_routes.router)
    router.include_router(objects_routes.router)
    router.include_router(metrics_routes.router)
    router.include_router(bundles_routes.router)
    router.include_router(graph_routes.router)
    router.include_router(rdf_routes.router)
    router.include_router(objectsearch_routes.router)
    router.include_router(review_routes.router)
    router.include_router(datasources_routes.router)
    router.include_router(webhooks_routes.router)
    return router


def register_platform() -> None:
    """StandardPlatform 에서 들인 것의 **등록** — SP `main.py` 의 `_register_extensions` 그대로
    (ADR 0008). 서버 화면 · 홈에만 쓰이던 등록(백업 경고 · 느린 요청 · 자기소개)은 그 화면을
    들일 때 더한다. 여러 번 불러도 안전하다(같은 것을 두 번 넣지 않는다) — 워커도 부른다."""
    extensions.register_stats(files_services.stats)
    # **부서를 지울 때 첨부 · 객체가 목록에 뜬다.** 안 걸면 FK 가 RESTRICT 라 500 이 난다.
    extensions.register_workspace_reference(files_services.workspace_reference)
    extensions.register_workspace_reference(objects_services.workspace_reference)
    # **부서를 통폐합할 때 자료를 넘기는 길.**
    extensions.register_workspace_content(objects_services.workspace_content)
    extensions.register_workspace_content(files_services.workspace_content)
    extensions.register_workspace_content(datasources_services.workspace_content)
    extensions.register_workspace_content(metrics_services.workspace_content)
    extensions.register_attachment_owner("objects", objects_attachments.owner)
    extensions.register_maintenance(objects_quality.maintenance)
    extensions.register_stats(objects_quality.stats)
    extensions.register_maintenance(objects_misses.maintenance)
    for provider in (*objects_review.PROVIDERS, *review_links.PROVIDERS):
        review_registry.register(provider)
    # `system` 타입이 비추는 원 표 — 부서 · 계정.
    system_sources.register_system_source(workspaces_services.SYSTEM_SOURCE)
    system_sources.register_system_source(accounts_system.SYSTEM_SOURCE)
    # CompCore 의 부품 · 지그 — 기준정보(SP 에서 받은 제품 · 프로젝트 …)가 이것을 가리킨다.
    system_sources.register_system_source(parts_system.SYSTEM_SOURCE)
    system_sources.register_system_source(jigs_system.SYSTEM_SOURCE)
    # 내 작업 — 태그가 작업에 객체를 붙인다(ADR 0011). **요청의 사람으로 거른다**(주인만).
    system_sources.register_system_source(works_system.SYSTEM_SOURCE)
    # 템플릿 — 태그가 붙는다. 내 템플릿은 주인만 본다(공용은 모두).
    system_sources.register_system_source(templates_system.SYSTEM_SOURCE)
    # 변경 이벤트(감사 기록이 커밋된 뒤)를 웹훅 · 지켜보기가 듣는다.
    events.register_listener(webhooks_services.on_events, in_jobs="summary")
    events.register_listener(objects_watches.on_events)
    extensions.register_stats(webhooks_services.stats)
    extensions.register_maintenance(datasources_services.maintenance)
    extensions.register_stats(datasources_services.stats)
    extensions.register_maintenance(webhooks_services.maintenance)
    extensions.register_maintenance(tasks_services.maintenance)
    extensions.register_stats(tasks_services.stats)
    extensions.register_maintenance(metrics_services.maintenance)
    extensions.register_stats(metrics_services.stats)
    extensions.register_profile_facts(ontology_profile.facts)
    extensions.register_profile_facts(datasources_services.profile_facts)
    extensions.register_profile_facts(metrics_services.profile_facts)

    # **기계 자격(PAT)의 범위** — SP 와 같다. 정의와 데이터를 가른다. CompCore 의 `write`
    # 범위는 여전히 모든 쓰기를 연다(`shared/auth.py`).
    scopes.register_write_scope("/api/ontology", "ontology:write")
    scopes.register_write_scope("/api/objects", "objects:write")
    scopes.register_write_scope("/api/bundles", "objects:write")
    scopes.register_write_scope("/api/tasks", "objects:write")
    scopes.register_write_scope("/api/attachments", "objects:write")
    scopes.register_write_scope("/api/tags", "objects:write")
    for pattern in (
        "/api/ontology/export",
        "/api/bundles/export",
        "/api/objects/*/export",
        "/api/objects/*/relations/export",
    ):
        scopes.register_read_only_post_pattern(pattern)
    scopes.register_read_only_post_pattern("/api/objects/*/resolve-many")
    scopes.register_read_only_post("/api/rdf/query")
    scopes.register_read_scope("/api/core", coreapi_routes.SCOPE)
    scopes.register_write_scope("/api/datasources", "objects:write")
    scopes.register_write_scope("/api/metrics", "ontology:write")
    scopes.register_read_only_post("/api/metrics/plan")
    scopes.register_write_scope("/api/review", "objects:write")
    scopes.register_read_only_post("/api/review/plan")
    # CompCore 의 것 — 레시피 검증 · 미리보기는 POST 지만 아무것도 안 바꾼다.
    scopes.register_read_only_post("/api/cad/recipe/")


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

    def read() -> str:
        html = index.read_text(encoding="utf-8").replace("<head>", f"<head>\n    {metas}", 1)
        return re.sub(
            r"<title>.*?</title>",
            f"<title>{html_escape(settings.app_name)}</title>",
            html,
            count=1,
        )

    # **빌드가 바뀌면 다시 읽는다**(파일 시각으로). 기동할 때 한 번만 읽어 두면, 서버가 도는
    # 동안 프론트를 다시 빌드했을 때 옛 index.html 이 이제 없는 `assets/index-<옛 해시>.js` 를
    # 가리켜 화면이 비었다(2026-10-26 — 개발 서버에서 겪었다). 빌드 도중(파일이 잠깐 없을 때)은
    # 앞의 것을 낸다.
    cached = {"stamp": index.stat().st_mtime_ns, "html": read()}

    def current() -> str:
        try:
            stamp = index.stat().st_mtime_ns
            if stamp != cached["stamp"]:
                cached.update(stamp=stamp, html=read())
        except FileNotFoundError:
            pass
        return str(cached["html"])

    portal = settings.portal_system_id if settings.portal_jwks_url.strip() else ""

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    def spa(full_path: str, request: Request) -> HTMLResponse:
        if full_path.startswith("api/"):
            raise NotFound(
                code("COMMON", 404),
                "존재하지 않는 엔드포인트입니다.",
                details={"path": f"/{full_path}"},
            )
        # **요청마다** 접두어를 심는다 — 같은 설치를 루트로도, 포털 뒤(`/compcore/`)로도 연다.
        # `<base>` 가 없으면 빌드의 상대 경로(`./assets/…`)가 깊은 주소(`/works/…`)에서
        # `/works/assets/…` 로 풀려 새로 고침 · 화면 링크가 빈 화면이 된다.
        prefix = url_prefix(request)
        head = [
            f'<base href="{html_escape(prefix)}/" />',
            f'<meta name="app-base" content="{html_escape(prefix)}" />',
        ]
        if portal:
            # 화면이 포털 세션으로 launch 토큰을 받을 타일 id — 비면 포털 로그인 단추가 없다.
            head.append(f'<meta name="portal-system" content="{html_escape(portal)}" />')
        page = current().replace("<head>", "<head>\n    " + "\n    ".join(head), 1)
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    logger.info("SPA 서빙: %s", dist)


def _guard_production_secrets(settings: Settings) -> None:
    if settings.app_env != "production":
        return
    if settings.jwt_secret == Settings.model_fields["jwt_secret"].default:
        raise RuntimeError(
            "JWT_SECRET이 기본값입니다. .env에 난수 값을 설정한 후 다시 시작하십시오."
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
                f"{label}에 쓸 수 없습니다: {path} ({failure.strerror})"
            ) from failure


def _describe_auth(app: FastAPI) -> None:
    """`/api/docs` 의 **Authorize** 단추가 PAT 으로 돌게 한다.

    우리 인증은 의존성 하나(`current_user`)라 FastAPI 가 스스로 알아내지 못한다. 적어 두지
    않으면 문서를 연 사람이 「어떻게 붙지」 를 코드에서 찾아야 한다 — 공개 API 라면서."""
    original = app.openapi

    def described() -> dict[str, Any]:
        spec = original()
        spec.setdefault("components", {})["securitySchemes"] = {
            "PAT": {
                "type": "http",
                "scheme": "bearer",
                "description": (
                    "개인 토큰(PAT) 또는 로그인 세션의 액세스 토큰. "
                    "PAT 은 화면의 「내 정보 → 토큰」 에서 만든다."
                ),
            }
        }
        spec["security"] = [{"PAT": []}]
        return spec

    app.openapi = described  # type: ignore[method-assign]


def create_app() -> FastAPI:
    settings = get_settings()
    _guard_writable_paths(settings)
    setup_logging(settings)
    _guard_production_secrets(settings)

    # **문서는 코드에서 자란다.** 묶음 설명과 머리말은 `api_docs` 한 곳에만 적는다 —
    # `/api/docs`(사람) 와 `/api/openapi.json`(기계)가 둘 다 거기서 나온다.
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=version.current(),
        description=api_docs.DESCRIPTION,
        openapi_tags=api_docs.TAGS,
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    _describe_auth(app)

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
    register_platform()
    app.include_router(_api_router(settings))
    _mount_spa(app, settings)  # SPA catch-all 은 반드시 API 라우터 뒤

    warn_if_behind(engine)
    logger.info(
        "%s (%s) 기동 (env=%s)", settings.app_name, settings.app_slug, settings.app_env
    )
    return app


app = create_app()
