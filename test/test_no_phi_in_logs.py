"""Report generation must not write clinical text to the logs."""

import asyncio
import logging
import os

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "ca-central-1")
os.environ["LANGFUSE_ENABLED"] = "false"

from app.schemas.report import QAItem, ReportGenerationRequest  # noqa: E402
from app.services import report as report_module  # noqa: E402
from app.services.report import ReportGenerationService  # noqa: E402

ANSWER_MARKER = "ZZTESTMARKER-answer"
PROMPT_MARKER = "ZZTESTMARKER-prompt"
OUTPUT_MARKER = "ZZTESTMARKER-output"


class FakeComprehendClient:
    """Finds one PIN in each text, so the redaction path runs."""

    def detect_pii_entities(self, Text, LanguageCode):
        return {"Entities": [{"Score": 0.99, "Type": "PIN", "BeginOffset": 0, "EndOffset": 4}]}


class FakeLLM:
    async def generate(self, messages, callbacks=None):
        return OUTPUT_MARKER, {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}


def test_report_generation_logs_no_clinical_text(monkeypatch, caplog):
    monkeypatch.setattr(report_module.comprehend_service, "client", FakeComprehendClient())
    monkeypatch.setattr(report_module.comprehend_service, "entity_types", ["PIN"])
    service = ReportGenerationService(document_record_repo=None)
    service.llm_service = FakeLLM()
    request = ReportGenerationRequest(
        prompt=PROMPT_MARKER,
        qas=[QAItem(question="Pain?", answer=f"Back pain {ANSWER_MARKER}")],
        scores={"health": "42.5"},
    )

    caplog.set_level(logging.DEBUG)
    for name in ("app.services.report", "app.services.comprehend"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    response = asyncio.run(service.generate_report(request))

    assert response.message == OUTPUT_MARKER
    assert caplog.records, "expected metadata log records"
    logged = "\n".join(record.getMessage() for record in caplog.records)
    for value in (ANSWER_MARKER, PROMPT_MARKER, OUTPUT_MARKER, "Back pain", "42.5"):
        assert value not in logged, f"{value!r} was logged"
