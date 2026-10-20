import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
import app.main as main_module


@pytest.fixture
def client(monkeypatch):
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestSession = sessionmaker(
        bind=test_engine,
        autocommit=False,
        autoflush=False,
    )

    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    # Tests must not require a running MinIO instance.
    monkeypatch.setattr(
        main_module,
        "ensure_bucket_exists",
        lambda: None,
    )

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def test_home(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "message" in response.json()


def test_upload_and_list(client, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "upload_object",
        lambda **kwargs: None,
    )

    response = client.post(
        "/documents",
        files={
            "file": (
                "report.pdf",
                io.BytesIO(b"%PDF-1.4 test"),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["filename"] == "report.pdf"

    listing = client.get("/documents")

    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_reject_unsupported_extension(client):
    response = client.post(
        "/documents",
        files={
            "file": (
                "malware.exe",
                io.BytesIO(b"test"),
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 400


def test_document_not_found(client):
    response = client.get("/documents/99999")

    assert response.status_code == 404