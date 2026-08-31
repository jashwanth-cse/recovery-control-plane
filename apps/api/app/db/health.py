from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

try:
    from redis import Redis
    from redis.exceptions import RedisError
except ImportError:
    Redis = None  # type: ignore[assignment]
    RedisError = Exception


@dataclass(frozen=True)
class DependencyCheck:
    status: str
    detail: str | None = None


def check_database(database_url: str) -> DependencyCheck:
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        engine.dispose()
        return DependencyCheck(status="ok")
    except SQLAlchemyError as exc:
        return DependencyCheck(status="error", detail=exc.__class__.__name__)


def check_redis(redis_url: str) -> DependencyCheck:
    if Redis is None:
        return DependencyCheck(status="error", detail="RedisClientUnavailable")

    try:
        client = Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        client.close()
        return DependencyCheck(status="ok")
    except RedisError as exc:
        return DependencyCheck(status="error", detail=exc.__class__.__name__)
