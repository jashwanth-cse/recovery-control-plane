from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.cases import router as cases_router
from app.api.baselines import router as baselines_router
from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.webhooks import router as webhooks_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    logger = get_logger(__name__)
    logger.info(
        "api_starting",
        extra={"app_name": settings.app_name, "environment": settings.app_env},
    )
    yield
    logger.info("api_stopping")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.7.0-phase6",
        summary="Revenue recovery cases with deterministic baseline evaluation.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(baselines_router)
    app.include_router(cases_router)
    app.include_router(dashboard_router)
    app.include_router(webhooks_router)
    return app


app = create_app()
