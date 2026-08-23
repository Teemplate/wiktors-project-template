"""Database engine and session factory.

Created lazily on purpose. `create_async_engine` does not open a connection, so
importing this module — and therefore importing `app.main` — never requires a
database. That is what lets `pytest` run the health tests on a fresh clone with
no Postgres and no .env at all.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    """Declarative base. Alembic autogenerate reads Base.metadata."""


engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency. One session per request, always closed."""
    async with SessionLocal() as session:
        yield session
