"""The S3 bucket is private: reference links to knowledge files must be pre-signed."""

import asyncio
import os
import uuid
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "ca-central-1")
os.environ["LANGFUSE_ENABLED"] = "false"

from app.core.config import settings  # noqa: E402
from app.services.chatbot import ChatbotService  # noqa: E402
from app.services.report import ReportGenerationService  # noqa: E402
from app.services.s3 import S3Service  # noqa: E402

BUCKET = settings.S3_BUCKET_NAME
REGION = settings.S3_REGION
BUCKET_HOST = f"{BUCKET}.s3.{REGION}.amazonaws.com"


def assert_presigned(url: str, path: str) -> None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    # The regional host: the backend re-signs only URLs of this form.
    assert parsed.hostname == BUCKET_HOST
    assert parsed.path == path
    assert query["X-Amz-Signature"][0] not in ("", "old")
    assert query["X-Amz-Expires"] == [str(settings.S3_PRESIGN_TTL_SECONDS)]


def test_s3_uri_becomes_presigned_url():
    url = S3Service().s3_uri_to_presigned_url(f"s3://{BUCKET}/knowledge/k1/guide v2.pdf")

    assert_presigned(url, "/knowledge/k1/guide%20v2.pdf")


def test_invalid_s3_uri_gives_no_url():
    service = S3Service()

    assert service.s3_uri_to_presigned_url("") is None
    assert service.s3_uri_to_presigned_url("https://example.com/x.pdf") is None


def test_stored_bucket_links_are_signed_again():
    service = S3Service()
    base = f"https://{BUCKET_HOST}/knowledge/k1/guide%20v2.pdf"

    assert_presigned(service.sign_https_url(base), "/knowledge/k1/guide%20v2.pdf")
    expired = service.sign_https_url(f"{base}?X-Amz-Expires=900&X-Amz-Signature=old")
    assert_presigned(expired, "/knowledge/k1/guide%20v2.pdf")
    with_page = service.sign_https_url(f"{base}#page=3")
    assert urlparse(with_page).fragment == "page=3"


def test_other_links_are_unchanged():
    service = S3Service()

    for url in [
        "",
        "https://example.com/guide?a=1&b=2",
        f"https://other-bucket.s3.{REGION}.amazonaws.com/x.pdf",
        f"http://{BUCKET_HOST}/x.pdf",
        f"https://{BUCKET_HOST}/",
    ]:
        assert service.sign_https_url(url) == url


class FakeDocumentRecordRepo:
    async def get_file_info_by_filenames(self, filenames, knowledge_id):
        return [{"filename": f, "title": f"Title of {f}", "sub_references": []} for f in filenames]


def test_insight_references_are_presigned():
    service = ReportGenerationService(document_record_repo=FakeDocumentRecordRepo())

    items = asyncio.run(service._build_reference_items(["guide.pdf"], "k1"))

    assert [item.title for item in items] == ["Title of guide.pdf"]
    assert_presigned(items[0].url, "/knowledge/k1/guide.pdf")


class FakeMessageRepo:
    def __init__(self, references):
        self.model = SimpleNamespace(
            to_dict=lambda: {"message_id": str(uuid.uuid4()), "references": references}
        )

    async def get_by_session(self, session_id, page, per_page, order):
        return [self.model], {"page": page}


def test_chat_history_reference_links_are_signed_again():
    stored = [
        {"title": "Guide", "url": f"https://{BUCKET_HOST}/knowledge/k1/guide.pdf"},
        {"title": "Web", "url": "https://example.com/page"},
    ]
    service = ChatbotService(
        session_repo=None, message_repo=FakeMessageRepo(stored), document_record_repo=None
    )

    messages, _ = asyncio.run(service.get_session_messages(str(uuid.uuid4())))

    refs = messages[0]["references"]
    assert_presigned(refs[0]["url"], "/knowledge/k1/guide.pdf")
    assert refs[1]["url"] == "https://example.com/page"
    # The stored list is not changed.
    assert stored[0]["url"] == f"https://{BUCKET_HOST}/knowledge/k1/guide.pdf"
