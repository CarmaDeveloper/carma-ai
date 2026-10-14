"""Free text must be redacted before it reaches the LLM, on every AI endpoint."""

import asyncio
import os
import re
import uuid

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "ca-central-1")
os.environ["LANGFUSE_ENABLED"] = "false"

import pytest  # noqa: E402
from botocore.exceptions import EndpointConnectionError  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.schemas.letter import LetterGenerationRequest  # noqa: E402
from app.schemas.report import (  # noqa: E402
    InsightGenerationRequest,
    QAItem,
    ReportGenerationRequest,
)
from app.services import chatbot as chatbot_module  # noqa: E402
from app.services.chatbot import ChatbotService  # noqa: E402
from app.services.comprehend import comprehend_service  # noqa: E402
from app.services.letter import LetterService  # noqa: E402
from app.services.report import ReportGenerationService  # noqa: E402
from app.services.template import TemplateService  # noqa: E402

# Synthetic identifiers only.
PATIENT_NAME = "John Doe"
PHONE = "403-555-0199"
HEALTH_NUMBER = "12345-6789"
PATIENT_DOB = "1980-03-14"
PII_NOTE = f"{PATIENT_NAME}, {PHONE}, PHN {HEALTH_NUMBER}. Back pain for weeks."
IDENTIFIERS = [PATIENT_NAME, PHONE, HEALTH_NUMBER]


class FakeComprehendClient:
    """Finds the synthetic name, phone and health number, like Comprehend would."""

    ENTITIES = (
        (PATIENT_NAME, "NAME"),
        (PHONE, "PHONE"),
        (HEALTH_NUMBER, "CA_HEALTH_NUMBER"),
    )

    def __init__(self):
        self.calls = []

    def detect_pii_entities(self, Text, LanguageCode):
        self.calls.append(Text)
        entities = []
        for value, entity_type in self.ENTITIES:
            for match in re.finditer(re.escape(value), Text):
                entities.append(
                    {
                        "Score": 0.99,
                        "Type": entity_type,
                        "BeginOffset": match.start(),
                        "EndOffset": match.end(),
                    }
                )
        return {"Entities": entities}


class BrokenComprehendClient:
    def detect_pii_entities(self, Text, LanguageCode):
        raise EndpointConnectionError(endpoint_url="https://comprehend.ca-central-1")


class FakeLLM:
    """Keeps the text of every prompt it receives."""

    model_id = "fake-model"

    def __init__(self):
        self.prompts = []

    def _record(self, messages):
        self.prompts.append("\n".join(str(message.content) for message in messages))

    async def generate(self, messages, callbacks=None):
        self._record(messages)
        return "Title", {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}

    async def generate_stream(self, messages, callbacks=None):
        self._record(messages)
        yield "output", None

    def all_text(self):
        return "\n".join(self.prompts)


class FakeMessageRepository:
    def __init__(self):
        self.saved = []

    async def create(self, **kwargs):
        self.saved.append(kwargs["content"])
        return None

    async def get_by_session(self, *args, **kwargs):
        return [], {}

    async def get_count_by_session(self, session_id):
        return len(self.saved)


class FakeSessionRepository:
    async def create(self, **kwargs):
        return None

    async def update_access_time(self, session_id):
        return None


@pytest.fixture
def fake_comprehend(monkeypatch):
    client = FakeComprehendClient()
    monkeypatch.setattr(comprehend_service, "client", client)
    monkeypatch.setattr(
        comprehend_service, "entity_types", Settings.model_fields["COMPREHEND_TYPES"].default
    )
    return client


@pytest.fixture
def broken_comprehend(monkeypatch):
    monkeypatch.setattr(comprehend_service, "client", BrokenComprehendClient())


@pytest.fixture
def fake_llm():
    return FakeLLM()


def report_items():
    return [
        {
            "category": {"name": "Pain", "scores": [{"name": "Pain score", "value": "7"}]},
            "patientResponse": [
                {
                    "question": {
                        "title": "Describe your symptoms",
                        "type": "Text",
                        "patientTextResponse": PII_NOTE,
                    }
                }
            ],
            "hcpNotes": PII_NOTE,
            "patientNote": PII_NOTE,
        }
    ]


def patient_information():
    return {"fullName": "Janet Example", "birthDay": PATIENT_DOB}


def assert_redacted(text):
    assert text, "the LLM received no prompt"
    for value in IDENTIFIERS:
        assert value not in text, f"{value!r} reached the LLM"
    assert "[REDACTED]" in text
    assert "Back pain" in text


async def collect(stream):
    return [event async for event in stream]


def run_report_generate(fake_llm, prompt=f"Summary for {PATIENT_NAME}"):
    service = ReportGenerationService(document_record_repo=None)
    service.llm_service = fake_llm
    request = ReportGenerationRequest(
        prompt=prompt,
        qas=[
            QAItem(
                question=f"Symptoms of {PATIENT_NAME}?",
                answer=PII_NOTE,
                sub_questions=[QAItem(question="Contact", answer=PHONE)],
            )
        ],
    )
    return asyncio.run(service.generate_report(request))


def run_insight(fake_llm):
    service = ReportGenerationService(document_record_repo=None)
    service.llm_service = fake_llm
    request = InsightGenerationRequest(
        report=report_items(),
        prompt=f"Insights for {PATIENT_NAME}",
        patientInformation=patient_information(),
    )
    return asyncio.run(collect(service.stream_insight_generation(request)))


def run_letter(fake_llm):
    service = LetterService(llm_service=fake_llm)
    request = LetterGenerationRequest(
        report=report_items(),
        instructions=f"Referral for {PATIENT_NAME}, PHN {HEALTH_NUMBER}.",
        patientInformation=patient_information(),
    )
    return asyncio.run(collect(service.stream_letter_generation(request)))


def run_template(fake_llm):
    service = TemplateService(llm_service=fake_llm)
    return asyncio.run(
        collect(service.stream_template_generation(f"Back pain intake for {PII_NOTE}"))
    )


def run_chat(fake_llm, messages, session_id=None):
    service = ChatbotService(
        session_repo=FakeSessionRepository(),
        message_repo=messages,
        document_record_repo=None,
    )
    service.llm_service = fake_llm
    return asyncio.run(
        collect(
            service.stream_chat(
                message=PII_NOTE, session_id=session_id, use_rag=False
            )
        )
    )


def event_types(events):
    return [event_type for event_type, _ in events]


def test_default_comprehend_types_cover_direct_identifiers():
    types = Settings.model_fields["COMPREHEND_TYPES"].default
    for entity_type in (
        "NAME",
        "ADDRESS",
        "PHONE",
        "EMAIL",
        "CA_HEALTH_NUMBER",
        "CA_SOCIAL_INSURANCE_NUMBER",
    ):
        assert entity_type in types
    assert "DATE_TIME" not in types
    assert "AGE" not in types


def test_report_generate_redacts_questions_answers_and_prompt(fake_comprehend, fake_llm):
    run_report_generate(fake_llm)

    assert_redacted(fake_llm.all_text())


def test_insight_redacts_report_and_prompt(fake_comprehend, fake_llm):
    events = run_insight(fake_llm)

    assert "insight.complete" in event_types(events)
    assert_redacted(fake_llm.all_text())


def test_letter_redacts_instructions_and_report(fake_comprehend, fake_llm):
    events = run_letter(fake_llm)

    assert "letter.complete" in event_types(events)
    assert_redacted(fake_llm.all_text())


def test_template_redacts_prompt(fake_comprehend, fake_llm):
    events = run_template(fake_llm)

    assert "template.complete" in event_types(events)
    assert len(fake_llm.prompts) == 2
    for prompt in fake_llm.prompts:
        assert_redacted(prompt)


def test_chat_redacts_new_message_and_stores_it_redacted(
    fake_comprehend, fake_llm, monkeypatch
):
    monkeypatch.setattr(chatbot_module.web_search_service, "enabled", False)
    messages = FakeMessageRepository()

    events = run_chat(fake_llm, messages)

    assert "chatbot.complete" in event_types(events)
    assert len(fake_llm.prompts) == 2  # session title and answer
    for prompt in fake_llm.prompts:
        assert_redacted(prompt)
    assert_redacted(messages.saved[0])


def test_patient_information_is_not_put_into_prompts(fake_comprehend, fake_llm):
    run_insight(fake_llm)
    run_letter(fake_llm)

    text = fake_llm.all_text()
    assert len(fake_llm.prompts) == 2
    assert "Janet Example" not in text
    assert PATIENT_DOB not in text


def test_report_generate_fails_when_comprehend_fails(broken_comprehend, fake_llm):
    with pytest.raises(Exception):
        run_report_generate(fake_llm)

    assert fake_llm.prompts == []


@pytest.mark.parametrize(
    "run,error_event",
    [
        (run_insight, "insight.error"),
        (run_letter, "letter.error"),
        (run_template, "template.error"),
        (
            lambda llm: run_chat(llm, FakeMessageRepository(), str(uuid.uuid4())),
            "chatbot.error",
        ),
    ],
)
def test_streams_stop_when_comprehend_fails(broken_comprehend, fake_llm, run, error_event):
    events = run(fake_llm)

    assert error_event in event_types(events)
    assert fake_llm.prompts == []


def test_long_text_is_split_under_the_comprehend_size_limit(fake_comprehend):
    line = f"{PATIENT_NAME} has back pain. " * 100
    text = "\n".join([line] * 100)  # about 270 KB

    [redacted] = asyncio.run(comprehend_service.redact_texts([text]))

    assert len(fake_comprehend.calls) > 1
    assert all(len(call.encode("utf-8")) <= 100_000 for call in fake_comprehend.calls)
    assert PATIENT_NAME not in redacted
    assert redacted.count("\n") == text.count("\n")


def test_very_long_line_is_cut_at_a_space(fake_comprehend):
    line = ("x" * 24_990) + f" {PATIENT_NAME} " + ("y " * 20_000)

    [redacted] = asyncio.run(comprehend_service.redact_texts([line]))

    assert all(len(call.encode("utf-8")) <= 100_000 for call in fake_comprehend.calls)
    assert PATIENT_NAME not in redacted
