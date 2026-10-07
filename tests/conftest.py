import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app import main
from app.main import app
from app import worker


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr("app.main.SessionLocal", TestingSession)
    monkeypatch.setattr(worker, "SessionLocal", TestingSession)
    monkeypatch.setattr(worker, "OUTPUT_DIR", tmp_path / "certificates")
    monkeypatch.setattr(main, "TEMPLATE_DIR", tmp_path / "templates")
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(engine)
