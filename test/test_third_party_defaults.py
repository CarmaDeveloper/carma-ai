"""Third-party tools must be off unless they are configured on purpose."""

import asyncio
import os
import uuid

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "ca-central-1")
os.environ["LANGFUSE_ENABLED"] = "false"

import pytest  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.services import chatbot as chatbot_module  # noqa: E402
from app.services import web_search as web_search_module  # noqa: E402
from app.services.chatbot import ChatbotService  # noqa: E402
from app.services.web_search import WebSearchService  # noqa: E402


class FakeTavilyClient:
    instances = []

    def __init__(self, api_key):
        self.api_key = api_key
        FakeTavilyClient.instances.append(self)


@pytest.fixture
def fake_tavily(monkeypatch):
    FakeTavilyClient.instances = []
    monkeypatch.setattr(web_search_module, "TavilyClient", FakeTavilyClient)
    return FakeTavilyClient


@pytest.mark.parametrize("key", ["", "   ", "unknown", "UNKNOWN", None])
def test_web_search_is_disabled_without_a_real_key(monkeypatch, fake_tavily, key):
    monkeypatch.setattr(web_search_module.settings, "TAVILY_API_KEY", key)

    service = WebSearchService()

    assert service.enabled is False
    assert service.client is None
    assert fake_tavily.instances == []


def test_web_search_is_enabled_with_a_key(monkeypatch, fake_tavily):
    monkeypatch.setattr(web_search_module.settings, "TAVILY_API_KEY", "tvly-real-key")

    service = WebSearchService()

    assert service.enabled is True
    assert len(fake_tavily.instances) == 1


def test_langfuse_is_off_by_default():
    assert Settings.model_fields["LANGFUSE_ENABLED"].default is False


class FakeMessageRepository:
    async def create(self, **kwargs):
        return None

    async def get_by_session(self, *args, **kwargs):
        return [], {}


class FakeSessionRepository:
    async def update_access_time(self, session_id):
        return None


def test_chat_ignores_internet_search_when_web_search_is_disabled(monkeypatch):
    queries = []

    async def fake_generate_search_query(self, message, history):
        queries.append(message)
        return "query"

    async def fake_search(query):
        queries.append(query)
        return []

    monkeypatch.setattr(chatbot_module.web_search_service, "enabled", False)
    monkeypatch.setattr(chatbot_module.web_search_service, "search", fake_search)
    monkeypatch.setattr(ChatbotService, "_generate_search_query", fake_generate_search_query)
    service = ChatbotService(
        session_repo=FakeSessionRepository(),
        message_repo=FakeMessageRepository(),
        document_record_repo=None,
    )

    async def first_event():
        stream = service.stream_chat(
            message="Latest hypertension guideline for my patient?",
            session_id=str(uuid.uuid4()),
            use_rag=False,
            use_internet_search=True,
        )
        try:
            return await stream.__anext__()
        finally:
            await stream.aclose()

    event_type, _ = asyncio.run(first_event())

    assert event_type == "chatbot.session"
    assert queries == []
