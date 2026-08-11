import pytest
from app import models  # noqa: F401
from app.core.database import Base, get_session
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture(autouse=True)
def force_free_image_provider(monkeypatch):
    """The test suite must never be able to reach a paid image provider."""
    from app.core.config import get_settings

    monkeypatch.setenv("IMAGE_GENERATION_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class MemoryObjectStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, content: bytes, content_type: str) -> None:
        if key in self.objects:
            raise AssertionError("object keys must never be overwritten")
        self.objects[key] = content

    def get(self, key: str) -> bytes:
        return self.objects[key]


class MemoryJobDispatcher:
    def __init__(self):
        self.job_ids = []

    def enqueue(self, job_id):
        self.job_ids.append(job_id)


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db_session:
        yield db_session
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(session: Session) -> TestClient:
    from app.assets.storage import get_object_storage
    from app.jobs.queue import get_job_dispatcher

    app = create_app()
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_job_dispatcher] = lambda: dispatcher
    with TestClient(app) as test_client:
        yield test_client
