"""Application factory and Uvicorn entry point."""

from __future__ import annotations

import logging
import re
import time
import uuid

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .api.deps import AppState
from .api.routes import router
from .config import Settings, get_settings
from .db import make_engine, make_session_factory
from .errors import ApiError
from .models import Base
from .providers.base import Providers
from .providers.factory import build_providers
from .seed import seed_demo
from .services.captures import CaptureService
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
    if settings.seed_demo_data and (settings.app_env == "development" or settings.demo_mode):
        seed_demo(sf)
    store = AudioStore(settings.audio_storage_dir)
    store.purge_older_than(settings.audio_retention_hours)
    providers = providers or build_providers(settings)

    app = FastAPI(title="BolBazaar API", version=__version__,
                  description="Voice-first visit, order and commitment capture. AI proposes; the application commits.")
    app.state.ctx = AppState(settings=settings, sf=sf, providers=providers, store=store,
                             captures=CaptureService(sf, providers, settings, store),
                             metrics=MetricsService(sf, providers), records=RecordsService(sf))
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                       allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-Id"])

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

    def envelope(request: Request, status: int, code: str, message: str, details=None) -> JSONResponse:
        rid = getattr(request.state, "request_id", uuid.uuid4().hex)
        return JSONResponse({"error": {"code": code, "message": message, "details": details}, "requestId": rid},
                            status_code=status, headers={"X-Request-Id": rid})

    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError):
        return envelope(request, error.status, error.code, str(error), error.details)

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
        return {"status": "ok", "version": __version__, "providers": providers.label}

    app.include_router(router)
    return app


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings()
    uvicorn.run("bolbazaar.main:app_factory", factory=True, host=settings.host, port=settings.port)


def app_factory() -> FastAPI:
    return create_app()
