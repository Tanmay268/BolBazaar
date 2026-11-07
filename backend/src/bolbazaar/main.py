"""Application factory and Uvicorn entry point."""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__, audio as audio_module
from .api.deps import AppState
from .api.routes import router
from .config import Settings, get_settings
from .costguard import CostGuard
from .db import make_engine, make_session_factory
from .errors import ApiError
from .guard import GuardMiddleware, SlidingWindowLimiter
from .models import Base
from .providers.base import Providers
from .providers.factory import build_providers
from .seed import ensure_demo_accounts, seed_demo
from .services.accounts import AccountService
from .services.bugs import BugService
from .services.captures import CaptureService
from .services.catalogue import CatalogueService
from .services.metrics import MetricsService
from .services.records import RecordsService
from .storage import AudioStore

LOGGER = logging.getLogger("bolbazaar.http")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


def create_app(settings: Settings | None = None, providers: Providers | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.jwt_key  # fail fast outside development when no secret is configured
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    sf = make_session_factory(engine)
    for warning in settings.warnings():
        LOGGER.warning("security_config %s", warning)
    if settings.seed_demo_data and (settings.app_env == "development" or settings.demo_mode):
        seed_demo(sf, password=settings.demo_password, admin_password=settings.admin_password or None)
        ensure_demo_accounts(sf, settings.demo_password, settings.admin_password or None)
    store = AudioStore(settings.audio_storage_dir)
    store.purge_older_than(settings.audio_retention_hours)
    providers = providers or build_providers(settings)
    audio_module.FFMPEG_SLOTS = threading.BoundedSemaphore(max(1, settings.ffmpeg_max_concurrent))
    guard, limiter = CostGuard(sf, settings), SlidingWindowLimiter()
    catalogue = CatalogueService(sf, settings, guard, providers)

    docs = None if settings.docs_enabled else False
    app = FastAPI(title="BolBazaar API", version=__version__,
                  description="Voice-first visit, order and commitment capture. AI proposes; the application commits.",
                  docs_url="/docs" if settings.docs_enabled else None, redoc_url="/redoc" if settings.docs_enabled else None,
                  openapi_url="/openapi.json" if settings.docs_enabled else None)
    app.state.ctx = AppState(settings=settings, sf=sf, providers=providers, store=store,
                             captures=CaptureService(sf, providers, settings, store, guard, catalogue),
                             metrics=MetricsService(sf, providers, guard), records=RecordsService(sf),
                             accounts=AccountService(sf, settings, guard), guard=guard, limiter=limiter, catalogue=catalogue,
                             bugs=BugService(sf, settings, guard))
    # Added before CORS so that CORS wraps it: 413/429 responses still carry CORS headers the browser can read.
    app.add_middleware(GuardMiddleware, settings=settings, limiter=limiter)
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-Id"],
                       expose_headers=["X-Request-Id", "Retry-After"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        started = time.monotonic()
        supplied = request.headers.get("X-Request-Id", "")
        request.state.request_id = supplied if REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-Id"] = request.state.request_id
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", "unmatched")
            LOGGER.info("http request_id=%s method=%s route=%s status=%s ms=%s", request.state.request_id,
                        request.method, route, status, round((time.monotonic() - started) * 1000))

    def envelope(request: Request, status: int, code: str, message: str, details=None, headers=None) -> JSONResponse:
        rid = getattr(request.state, "request_id", uuid.uuid4().hex)
        return JSONResponse({"error": {"code": code, "message": message, "details": details}, "requestId": rid},
                            status_code=status, headers={"X-Request-Id": rid, **(headers or {})})

    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError):
        return envelope(request, error.status, error.code, str(error), error.details, error.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        fields = [{"path": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in error.errors()]
        return envelope(request, 422, "VALIDATION_ERROR", "The request is not valid", fields)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception):
        LOGGER.exception("unhandled error request_id=%s", getattr(request.state, "request_id", "-"))
        return envelope(request, 500, "INTERNAL_ERROR", "Something went wrong")

    @app.get("/health", tags=["operations"])
    def health():
        # Provider wiring is only disclosed in development: it tells an attacker which endpoints cost money.
        body = {"status": "ok", "version": __version__}
        if settings.app_env == "development":
            body["providers"] = providers.label
        return body

    app.include_router(router)
    return app


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings()
    uvicorn.run("bolbazaar.main:app_factory", factory=True, host=settings.host, port=settings.port)


def app_factory() -> FastAPI:
    return create_app()
