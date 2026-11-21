"""
Pytest configuration for DeskBuddy Backend tests.
"""
import pytest
import asyncio
from typing import AsyncGenerator
from httpx import ASGITransport, AsyncClient
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.config import settings
from app.core.database import Base, engine, get_db
from app.core.database import async_session_maker


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def override_get_db(db_session: AsyncSession):
    """Override get_db dependency for testing."""
    async def _override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def async_client(override_get_db) -> AsyncGenerator[AsyncClient, None]:
    """Async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def test_client(override_get_db) -> TestClient:
    """Sync test client."""
    return TestClient(app)


# Override settings for testing
@pytest.fixture(autouse=True)
def test_settings():
    """Override settings for testing."""
    settings.debug = True
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    settings.enable_pc_monitoring = False
    settings.enable_music_control = False
    settings.enable_calendar = False
    settings.enable_voice_assistant = False
    settings.enable_desk_mate = False
    settings.enable_hardware_bridge = False
    settings.nvidia_api_key = "test-key"
    yield
    # Restore settings after test
    settings.debug = False
    settings.database_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/deskbuddy"
    settings.enable_pc_monitoring = True
    settings.enable_music_control = True
    settings.enable_calendar = True
    settings.enable_voice_assistant = True
    settings.enable_desk_mate = True
    settings.enable_hardware_bridge = True