from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.health import check_database, check_redis

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    service: str
    environment: str
    status: str
    version: str


class DependencyStatus(BaseModel):
    status: str
    detail: str | None = None


class ReadinessResponse(HealthResponse):
    dependencies: dict[str, DependencyStatus]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        service=settings.app_name,
        environment=settings.app_env,
        status="ok",
        version="0.1.0-phase0",
    )


@router.get("/health/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return health()


@router.get("/health/ready", response_model=ReadinessResponse)
def ready(response: Response) -> ReadinessResponse:
    settings = get_settings()
    checks = {
        "database": check_database(settings.database_url),
        "redis": check_redis(settings.redis_url),
    }
    overall_status = (
        "ready"
        if all(item.status == "ok" for item in checks.values())
        else "degraded"
    )
    if overall_status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        service=settings.app_name,
        environment=settings.app_env,
        status=overall_status,
        version="0.1.0-phase0",
        dependencies={
            name: DependencyStatus(status=check.status, detail=check.detail)
            for name, check in checks.items()
        },
    )
