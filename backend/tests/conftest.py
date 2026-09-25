"""Pytest fixtures for backend tests."""
from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure tests use the in-process SQLite-friendly defaults.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-bytes-min-len-for-tests")

# In-memory SQLite for unit tests; integration tests use Postgres from docker-compose.
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()  # type: ignore[attr-defined]
_settings = get_settings()
_settings.database_url = TEST_DB_URL

# Force models to use the in-memory DB.
import app.db.session as session_module  # noqa: E402

_test_engine = create_async_engine(TEST_DB_URL, future=True)
session_module.engine = _test_engine
session_module.AsyncSessionLocal = async_sessionmaker(
    _test_engine, expire_on_commit=False, class_=AsyncSession
)

from app.models.base import Base  # noqa: E402


@pytest_asyncio.fixture(scope="function", autouse=True)
async def _setup_db() -> AsyncGenerator[None, None]:
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with session_module.AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def two_users(db: AsyncSession) -> tuple[dict, dict]:
    from app.core.security import create_access_token, hash_password
    from app.models import User

    a = User(username="alice", email=f"a-{uuid.uuid4().hex[:8]}@x.test", password_hash=hash_password("pw"))
    b = User(username="bob", email=f"b-{uuid.uuid4().hex[:8]}@x.test", password_hash=hash_password("pw"))
    db.add_all([a, b])
    await db.commit()
    for u in (a, b):
        await db.refresh(u)
    return (
        {"id": a.id, "username": a.username, "token": create_access_token(a.id)},
        {"id": b.id, "username": b.username, "token": create_access_token(b.id)},
    )
