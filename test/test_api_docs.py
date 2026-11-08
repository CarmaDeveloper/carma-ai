"""The API docs are internal: they must be off in production."""

import os

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "ca-central-1")
os.environ["LANGFUSE_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from main import create_application  # noqa: E402


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_are_off_in_production(monkeypatch, path):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    client = TestClient(create_application())

    assert client.get(path).status_code == 404


def test_api_docs_are_on_outside_production(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    client = TestClient(create_application())

    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
