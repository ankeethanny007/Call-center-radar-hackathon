from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base, db_session
from app.main import app
from app.models import Call
from app.security import require_media_access
from app.storage import storage


def test_api_token_protects_persisted_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    session.add(Call(id="protected-call", audio_path="audio/protected.mp3"))
    session.commit()
    session.close()

    def override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(settings, "api_access_token", "test-access-token")
    app.dependency_overrides[db_session] = override_db
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/calls").status_code == 401
            assert client.get("/api/v1/calls", headers={"X-API-Key": "test-access-token"}).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_local_audio_urls_use_short_lived_signatures_when_token_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_access_token", "test-access-token")
    monkeypatch.setattr(settings, "media_url_ttl_seconds", 60)
    monkeypatch.setattr(settings, "storage_provider", "local")
    relative_path = "audio/protected call.mp3"
    signed_url = storage.url_for(relative_path)
    parsed = urlparse(signed_url)
    query = parse_qs(parsed.query)
    require_media_access(relative_path, expires=int(query["expires"][0]), signature=query["signature"][0])
    with pytest.raises(HTTPException) as exc_info:
        require_media_access(relative_path, expires=int(query["expires"][0]), signature="invalid")
    assert exc_info.value.status_code == 401
