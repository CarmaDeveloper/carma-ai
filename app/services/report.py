"""Report generation service."""

import json
from typing import AsyncGenerator, Dict, List, Set, Optional, Tuple

from langchain_core.messages import HumanMessage
from langchain_core.documents import Document

from app.core.exceptions import ModelError
from app.core.langfuse import langfuse_context
from app.core.logging import setup_logger
from app.repositories import DocumentRecordRepositoryProtocol
from app.schemas.report import (
    QAItem,
    ReportGenerationRequest,
    ReportGenerationResponse,
    TokenUsage,
    InsightGenerationRequest,
    ReferenceItem,
)
from app.schemas.letter import ReportItem
from app.prompts.report import (
    RAG_PROMPT_TEMPLATE,
    NO_CONTEXT_PROMPT_TEMPLATE,
    NO_QAS_PROVIDED_TEXT,
    effective_prompt as compute_effective_prompt,
)
from app.prompts.insight import (
    INSIGHT_WITH_CONTEXT_TEMPLATE,
    INSIGHT_NO_CONTEXT_TEMPLATE,
    DEFAULT_INSIGHT_TASK,
)
from app.services.comprehend import comprehend_service
from app.services.llm import LLMService, ModelConfig
from app.services.s3 import s3_service
from app.services.vector_store import vector_store_service

logger = setup_logger(__name__)


class ReportGenerationService:
    """Service for generating reports using RAG."""

    def __init__(
        self,
        document_record_repo: DocumentRecordRepositoryProtocol,
    ) -> None:
        """
        Initialize the report generation service.

        Args:
            document_record_repo: Document record repository for fetching file metadata
        """
        self.llm_service = LLMService()
        self._document_record_repo = document_record_repo

    async def generate_report(
        self, request: ReportGenerationRequest, user_id: Optional[str] = None
    ) -> ReportGenerationResponse:
        """
        Generate a report based on the request.

        Args:
            request: Report generation request

        Returns:
            Generated report response

        Raises:
            ModelError: If model operations fail
            VectorStoreError: If vector store operations fail
        """
        # Get normalized scores for logging and processing
        # INPUT: request.scores = {"health": "85", "body": "70"} OR request.legacy_score = 85.5
        # OUTPUT: scores = {"health": 85.0, "body": 70.0} OR {"overall": 85.5}
        scores = request.get_scores()
        logger.info(
            f"Starting report generation: knowledge_id={request.knowledge_id}, "
            f"qa_count={len(request.qas)}, prompt_length={len(request.prompt)}, "
            f"scores={scores}"
        )

        try:
            # Step 1: Process answers through Comprehend for PII redaction
            # Extract all answers from hierarchical structure
            # INPUT: request.qas = [
            #   QAItem(question="How is your health?", answer="Good", sub_questions=[
            #       QAItem(question="Any conditions?", answer="Yes, diabetes", sub_questions=None)
            #   ])
            # ]
            # OUTPUT: answers = ["Good", "Yes, diabetes"]  (flat list of all answers recursively)
            answers = self._extract_all_answers(request.qas)

            # INPUT: answers = ["My name is John Doe", "Email: john@example.com"]
            # OUTPUT: redacted_answers = ["My name is [NAME]", "Email: [EMAIL]"]
            redacted_answers = await comprehend_service.redact_pii(answers)

            logger.info(
                f"Completed PII redaction: redacted_count={len(redacted_answers)}"
            )
            logger.info(f"Redacted answers: {redacted_answers}")

            # Step 2: Get context from vector store if knowledge_id provided
            # INPUT: knowledge_id = "kb-123", request.qas (questions extracted from it)
            # OUTPUT: context_docs = [
            #   Document(page_content="Diabetes treatment guidelines...", metadata={"file_name": "doc1.pdf", "document_id": "doc-123"}),
            #   Document(page_content="Blood sugar management...", metadata={"file_name": "doc2.pdf", "document_id": "doc-456"})
            # ]
            context_docs = []
            if request.knowledge_id:
                context_docs = await self._get_context(
                    request.knowledge_id, request.qas
                )
                logger.info(f"Retrieved context: doc_count={len(context_docs)}")

            # Step 3: Get references from context
            # INPUT: context_docs (list of Document objects with metadata)
            # OUTPUT: references = {"doc1.pdf", "doc2.pdf"}  (set of unique file names)
            references = self._extract_references(context_docs)

            # Step 4: Get document IDs from context
            # INPUT: context_docs (list of Document objects with metadata)
            # OUTPUT: document_ids = {"doc-123", "doc-456"}  (set of unique document IDs)
            document_ids = self._extract_document_ids(context_docs)
            logger.info(
                f"Extracted document IDs: doc_id_count={len(document_ids)}, ids={list(document_ids)}"
            )

            # Step 5: Generate report with direct model call to capture token usage
            # INPUT: request.qas, redacted_answers
            # OUTPUT: qa_text = """
            #   Question: How is your health?
            #   Answer: Good
            #
            #     Question: Any conditions?
            #     Answer: Yes, diabetes
            # """
            qa_text = self._format_qas(request.qas, redacted_answers)

            # Format scores for inclusion in prompt
            # INPUT: scores = {"health": 85.0, "body": 70.0}
            # OUTPUT: scores_text = "Scores:\nHealth Score: 85.0\nBody Score: 70.0"
            scores_text = self._format_scores(scores)

            # Log the full request before sending to Bedrock
            self._log_bedrock_request(request, qa_text, context_docs, scores_text)

            # Use direct model call to capture token usage
            # INPUT: request.prompt, context_docs, qa_text, scores_text
            # OUTPUT: message = "Based on the patient responses, here are the key findings..."
            #         token_usage = TokenUsage(input_tokens=1250, output_tokens=350, total_tokens=1600)
            message, token_usage = await self._generate_with_token_tracking(
                request.prompt, context_docs, qa_text, scores_text, user_id=user_id
            )

            logger.info(f"Generated report: message_length={len(message)}")
            logger.info(f"Message: {message}")
            if token_usage:
                logger.info(
                    f"Token usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}"
                )

            # FINAL OUTPUT: ReportGenerationResponse = {
            #   "message": "Based on the patient responses...",
            #   "references": ["doc1.pdf", "doc2.pdf"],
            #   "document_ids": ["doc-123", "doc-456"],
            #   "knowledge_id": "kb-123",
            #   "token_usage": {"input_tokens": 1250, "output_tokens": 350, "total_tokens": 1600}
            # }
            return ReportGenerationResponse(
                message=message,
                references=list(references),
                document_ids=list(document_ids),
                knowledge_id=request.knowledge_id,
                token_usage=token_usage,
            )

        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            raise

    async def stream_insight_generation(
        self, request: InsightGenerationRequest, user_id: Optional[str] = None
    ) -> AsyncGenerator[tuple[str, dict], None]:
        """
        Generate insights from report data and stream as events.

        Flow:
        1. Emit init event
        2. Retrieve RAG context (if knowledge_id provided)
        3. Emit metadata event with references, document_ids, knowledge_id
        4. Emit references event with title and S3 download URL for each reference
        5. Format report data for LLM readability
        6. Build prompt using insight templates
        7. Stream LLM response
        8. Emit complete/error event
        """
        logger.info(
            f"Starting insight generation: knowledge_id={request.knowledge_id}, "
            f"report_count={len(request.report)}, prompt_length={len(request.prompt or '')}"
        )

        yield ("insight.init", {"status": "started"})

        try:
            # Context Retrieval (only if knowledge_id provided)
            context_docs = []
            if request.knowledge_id:
                questions = self._extract_insight_questions(request.report)
                if questions:
                    context_docs = await vector_store_service.similarity_search(
                        knowledge_id=request.knowledge_id, queries=questions, k=4
                    )
                    logger.info(f"Retrieved RAG context: doc_count={len(context_docs)}")

            # Extract references and document_ids from context
            references = list(self._extract_references(context_docs))
            document_ids = list(self._extract_document_ids(context_docs))

            # Emit metadata event with references, document_ids, and knowledge_id
            yield (
                "insight.metadata",
                {
                    "references": references,
                    "document_ids": document_ids,
                    "knowledge_id": request.knowledge_id,
                },
            )

            # Emit references event with title and S3 download URL
            reference_items = []
            if references and request.knowledge_id:
                reference_items = await self._build_reference_items(
                    references, request.knowledge_id
                )
            yield (
                "insight.references",
                {
                    "references": [
                        {"title": ref.title, "url": ref.url}
                        for ref in reference_items
                    ]
                },
            )

            # Format report data for LLM (header once from request; report items from request.report)
            report_text = self._format_report_for_llm(request)

            # Determine user prompt
            # Use provided prompt or fall back to default
            user_prompt = (
                request.prompt.strip()
                if request.prompt and request.prompt.strip()
                else DEFAULT_INSIGHT_TASK
            )

            # Build final prompt using appropriate template
            if context_docs:
                # With RAG context
                context_text = self._format_context(context_docs)
                formatted_prompt = INSIGHT_WITH_CONTEXT_TEMPLATE.format(
                    user_prompt=user_prompt,
                    context=context_text,
                    report_data=report_text,
                )
            else:
                # Without RAG context
                formatted_prompt = INSIGHT_NO_CONTEXT_TEMPLATE.format(
                    user_prompt=user_prompt,
                    report_data=report_text,
                )

            # Stream LLM response
            messages = [HumanMessage(content=formatted_prompt)]

            # Use Langfuse context for insight generation with user tracking
            async with langfuse_context(
                user_id=user_id,
                trace_name="report.insight_generation",
                tags=["insight", "rag" if context_docs else "no_rag"],
                metadata={
                    "knowledge_id": request.knowledge_id,
                    "report_count": len(request.report),
                    "context_doc_count": len(context_docs),
                },
            ) as langfuse_handler:
                callbacks = [langfuse_handler] if langfuse_handler else None

                async for chunk, _ in self.llm_service.generate_stream(
                    messages, callbacks=callbacks
                ):
                    if chunk:
                        yield ("insight.content", {"content": chunk})

        except Exception as e:
            logger.error(f"Error generating insight: {e}", exc_info=True)
            yield ("insight.error", {"error": "Failed to generate insights"})
            return

        yield ("insight.complete", {"status": "complete"})

    def format_sse_event(self, event_type: str, data: dict) -> str:
        """
        Format data as Server-Sent Event with JSON payload.

        Args:
            event_type: Type of the event
            data: Dictionary data to send as JSON

        Returns:
            Formatted SSE string with JSON data
        """
        json_data = json.dumps(data)
        return f"event: {event_type}\ndata: {json_data}\n\n"

    def _extract_insight_questions(
        self, report_items: List[ReportItem]
    ) -> List[str]:
        """Extract question titles from report items for context retrieval."""
        questions = []
        for item in report_items:
            for response in item.patient_response or []:
                questions.append(response.question.title)
        return questions

    async def _build_reference_items(
        self, filenames: List[str], knowledge_id: str
    ) -> List[ReferenceItem]:
        """
        Build reference items with title and S3 download URL.

        Args:
            filenames: List of S3 filenames
            knowledge_id: Knowledge base identifier

        Returns:
            List of ReferenceItem with title and url
        """
        reference_items = []
        filename_to_title = {}
        try:
            # Fetch file info (title) from database using injected repository
            file_info_list = await self._document_record_repo.get_file_info_by_filenames(
                filenames, knowledge_id
            )

            # Create a mapping of filename to title
            filename_to_title = {
                info["filename"]: info["title"] for info in file_info_list
            }
        except Exception as e:
            logger.error(f"Failed to fetch file info for references, will use filenames as titles: {e}", exc_info=True)

        # Build reference items
        for filename in filenames:
            try:
                # Get title from database or use filename as fallback
                title = filename_to_title.get(filename)
                if title is None:
                    title = filename

                # Construct S3 URL and convert to HTTPS
                s3_url = s3_service.construct_s3_url(knowledge_id, filename)
                https_url = s3_service.s3_uri_to_https_url(s3_url)

                if https_url:
                    reference_items.append(
                        ReferenceItem(title=title, url=https_url)
                    )
                else:
                    logger.warning(
                        f"Failed to construct URL for file: {filename}"
                    )
            except Exception as e:
                logger.error(f"Failed to build reference item for file '{filename}', skipping. Error: {e}", exc_info=True)

        return reference_items

    def _format_report_for_llm(self, request: InsightGenerationRequest) -> str:
        """Convert report data to human-readable text for LLM. Header once from request; then each report item."""
        report_items = request.report
        if not report_items:
            return "No report data provided."

        lines = []

        # Header (once from top-level request)
        if request.questionnaire_title:
            lines.append(f"# {request.questionnaire_title}")
        if request.patient_information:
            pi = request.patient_information
            if pi.full_name or pi.birth_day:
                parts = []
                if pi.full_name:
                    parts.append(pi.full_name)
                if pi.birth_day:
                    parts.append(f"DOB: {pi.birth_day}")
                lines.append("Patient: " + ", ".join(parts))
        if request.completed_at:
            lines.append(f"Completed: {request.completed_at}")
        if lines:
            lines.append("")

        # Format each category
        for item in report_items:
            lines.append(f"## {item.category.name}")
            if item.category.scores:
                scores_str = ", ".join(f"{s.name}: {s.value}" for s in item.category.scores)
                lines.append(f"Scores: {scores_str}")
            if item.hcp_notes:
                lines.append(f"HCP Notes: {item.hcp_notes}")
            if item.patient_note:
                lines.append(f"Patient Note: {item.patient_note}")
            if item.community_resources:
                res_str = ", ".join(f"{r.title} ({r.url})" for r in item.community_resources)
                lines.append(f"Community Resources: {res_str}")
            lines.append("")

            # Patient Responses
            if item.patient_response:
                lines.append("### Patient Responses:")
                for i, resp in enumerate(item.patient_response, 1):
                    q = resp.question
                    lines.append(f"{i}. {q.title}")
                    if q.description:
                        lines.append(f"   Description: {q.description}")
                    lines.extend(self._format_answer_with_context(q))
                    lines.append("")

            # HCP Responses
            if item.hcp_response:
                lines.append("### HCP Responses:")
                for i, resp in enumerate(item.hcp_response, 1):
                    q = resp.question
                    lines.append(f"{i}. {q.title}")
                    if q.description:
                        lines.append(f"   Description: {q.description}")
                    lines.extend(self._format_answer_with_context(q))
                    lines.append("")

        return "\n".join(lines)

    def _format_answer_with_context(self, question) -> list[str]:
        """
        Format the answer with full context (available options, selected answer).

        Returns a list of lines to be added to the output.
        """
        lines = []

        # Multiple choice questions
        if question.options:
            options_text = ", ".join(opt.title for opt in question.options)
            lines.append(f"   Available Options: {options_text}")

            if question.selected_options:
                selected_text = ", ".join(opt.title for opt in question.selected_options)
                lines.append(f"   Selected: {selected_text}")
            else:
                lines.append("   Selected: (none)")
            return lines

        # Numeric scale questions
        if question.numeric_scale:
            scale = question.numeric_scale
            scale_info = f"{scale.min}-{scale.max}"
            if scale.label1 or scale.label3:
                scale_info += f" ({scale.label1} → {scale.label3})"
            lines.append(f"   Scale: {scale_info}")

            if question.selected_value is not None:
                lines.append(f"   Selected: {question.selected_value}")
            else:
                lines.append("   Selected: (none)")
            return lines

        # Text response
        if question.patient_text_response:
            lines.append(f"   Response: {question.patient_text_response}")
            return lines

        # Numeric value without scale context
        if question.selected_value is not None:
            lines.append(f"   Answer: {question.selected_value}")
            return lines

        lines.append("   Answer: (no response)")
        return lines

    async def _get_context(
        self, knowledge_id: str, qas: List[QAItem]
    ) -> List[Document]:
        """Retrieve context documents from vector store."""
        try:
            # Extract all questions from hierarchical structure for similarity search
            questions = self._extract_all_questions(qas)

            # If no questions, return empty context
            if not questions:
                logger.info("No questions provided, skipping context retrieval")
                return []

            # Perform similarity search
            return await vector_store_service.similarity_search(
                knowledge_id=knowledge_id,
                queries=questions,
                k=4,  # Retrieve top 4 documents per question
            )

        except Exception as e:
            logger.warning(
                f"Failed to retrieve context, continuing without: knowledge_id={knowledge_id}, error={str(e)}"
            )
            return []

    async def _generate_with_token_tracking(
        self, user_prompt, context_docs, qa_text, scores_text, user_id: Optional[str] = None
    ) -> tuple[str, Optional[TokenUsage]]:
        """Generate report with direct model call to capture token usage."""
        try:
            logger.info("Generating report with token tracking")
            # Determine effective prompt via prompts module helper
            effective_user_prompt = compute_effective_prompt(user_prompt)
            logger.info(f"User prompt (effective): {effective_user_prompt}")

            # Choose the appropriate prompt template based on whether we have context
            if context_docs:
                template = RAG_PROMPT_TEMPLATE
                logger.info("Using RAG prompt template (with context)")
                context_text = self._format_context(context_docs)
                formatted_prompt = template.format(
                    prompt=effective_user_prompt,
                    context=context_text,
                    qas=qa_text,
                    scores=scores_text,
                )
            else:
                template = NO_CONTEXT_PROMPT_TEMPLATE
                logger.info("Using no-context prompt template")
                formatted_prompt = template.format(
                    prompt=effective_user_prompt,
                    qas=qa_text,
                    scores=scores_text,
                )

            logger.info(f"Final formatted prompt: {formatted_prompt}")

            # Collect chunks and usage
            message = ""
            token_usage = None

            # Wrap prompt in HumanMessage as expected by LLMService
            messages = [HumanMessage(content=formatted_prompt)]

            # Use Langfuse context for report generation with user tracking
            async with langfuse_context(
                user_id=user_id,
                trace_name="report.generation",
                tags=["report", "rag" if context_docs else "no_rag"],
                metadata={
                    "qa_count": len(qa_text.split("Question:")),
                    "context_doc_count": len(context_docs) if context_docs else 0,
                },
            ) as langfuse_handler:
                callbacks = [langfuse_handler] if langfuse_handler else None

                # Generate the full report and get token usage
                message, usage = await self.llm_service.generate(
                    messages, callbacks=callbacks
                )
            
            token_usage = None
            if usage:
                token_usage = TokenUsage(
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                )

            return message, token_usage

        except Exception as e:
            logger.error(f"Failed to generate report with token tracking: {str(e)}")
            raise ModelError(f"Failed to generate report: {str(e)}")

    def _format_qas(self, qas: List[QAItem], redacted_answers: List[str]) -> str:
        """Format question-answer pairs for the prompt, preserving hierarchical structure."""
        if not qas:
            return NO_QAS_PROVIDED_TEXT

        # Build a flat list of all QA items in order with their depth
        qa_items = self._flatten_qas(qas)

        # Format each QA item with proper indentation
        formatted_qas = []
        for i, (qa, depth) in enumerate(qa_items):
            answer = redacted_answers[i] if i < len(redacted_answers) else qa.answer
            indent = "  " * depth  # 2 spaces per depth level
            formatted_qas.append(
                f"{indent}Question: {qa.question}\n{indent}Answer: {answer}"
            )

        return "\n\n".join(formatted_qas)

    def _flatten_qas(
        self, qas: List[QAItem], depth: int = 0
    ) -> List[Tuple[QAItem, int]]:
        """Recursively flatten hierarchical QA structure while preserving order and depth."""
        items = []
        for qa in qas:
            items.append((qa, depth))
            if qa.sub_questions:
                items.extend(self._flatten_qas(qa.sub_questions, depth + 1))
        return items

    def _extract_all_answers(self, qas: List[QAItem]) -> List[str]:
        """Recursively extract all answers from hierarchical QA structure."""
        answers = []
        for qa in qas:
            answers.append(qa.answer)
            if qa.sub_questions:
                answers.extend(self._extract_all_answers(qa.sub_questions))
        return answers

    def _extract_all_questions(self, qas: List[QAItem]) -> List[str]:
        """Recursively extract all questions from hierarchical QA structure."""
        questions = []
        for qa in qas:
            questions.append(qa.question)
            if qa.sub_questions:
                questions.extend(self._extract_all_questions(qa.sub_questions))
        return questions

    def _format_scores(self, scores: Optional[Dict[str, float]]) -> str:
        """Format scores for inclusion in the prompt."""
        if not scores:
            return "No scores provided."

        if len(scores) == 1 and "overall" in scores:
            return f"Overall Score: {scores['overall']}"
        else:
            formatted_scores = []
            for category, score in scores.items():
                formatted_scores.append(f"{category.title()} Score: {score}")
            return "Scores:\n" + "\n".join(formatted_scores)

    def _format_context(self, documents: List[Document]) -> str:
        """Format context documents for the prompt."""
        if not documents:
            return "No additional context available."

        context_parts = []
        for i, doc in enumerate(documents, 1):
            # Include metadata if available
            source_info = ""
            if doc.metadata:
                source = doc.metadata.get("source", "")
                if source:
                    source_info = f" (Source: {source})"

            context_parts.append(f"Context {i}{source_info}:\n{doc.page_content}")

        return "\n\n".join(context_parts)

    def _extract_references(self, documents: List[Document]) -> Set[str]:
        """Extract unique reference filenames from documents."""
        references = set()

        for doc in documents:
            if doc.metadata and "file_name" in doc.metadata:
                filename = doc.metadata["file_name"]
                if filename:
                    references.add(filename)

        return references

    def _extract_document_ids(self, documents: List[Document]) -> Set[str]:
        """Extract unique document IDs from documents."""
        document_ids = set()

        for doc in documents:
            if doc.metadata and "document_id" in doc.metadata:
                document_ids.add(doc.metadata["document_id"])

        return document_ids

    def _log_bedrock_request(self, request, qa_text, context_docs, scores_text):
        """Log the full request being sent to Bedrock including all prompts and context."""
        logger.info(f"=== BEDROCK REQUEST LOG ===")
        logger.info(f"Knowledge ID: {request.knowledge_id}")
        logger.info(f"Total QA pairs: {len(request.qas)}")
        logger.info(f"Total context documents: {len(context_docs)}")

        # Log the user prompt
        logger.info(f"User prompt: {request.prompt}")

        # Log the formatted QA text
        logger.info(f"Formatted QA pairs:")
        logger.info(f"{qa_text}")

        # Log the scores
        logger.info(f"Scores:")
        logger.info(f"{scores_text}")

        # Log context documents that will be sent
        logger.info(f"Context documents being sent:")
        for i, doc in enumerate(context_docs, 1):
            source_info = doc.metadata.get("source_file", "Unknown")
            doc_id = doc.metadata.get("document_id", "Unknown")
            logger.info(f"  Document {i} (from {source_info}, doc_id: {doc_id}):")
            logger.info(f"    Content: {doc.page_content[:300]}...")

        logger.info(f"=== END BEDROCK REQUEST LOG ===")


    def _extract_token_usage(self, response) -> Optional[TokenUsage]:
        """Extract token usage information from LangChain response."""
        # This method is no longer used by _generate_with_token_tracking but kept if needed for other methods
        try:
            # Check if response has usage_metadata attribute (LangChain format)
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage_metadata = response.usage_metadata

                # Handle both dict and object formats
                if isinstance(usage_metadata, dict):
                    input_tokens = usage_metadata.get(
                        "input_tokens", usage_metadata.get("prompt_tokens", 0)
                    )
                    output_tokens = usage_metadata.get(
                        "output_tokens", usage_metadata.get("completion_tokens", 0)
                    )
                    total_tokens = usage_metadata.get("total_tokens")
                    if total_tokens is None:
                        total_tokens = input_tokens + output_tokens
                else:
                    input_tokens = getattr(
                        usage_metadata,
                        "input_tokens",
                        getattr(usage_metadata, "prompt_tokens", 0),
                    )
                    output_tokens = getattr(
                        usage_metadata,
                        "output_tokens",
                        getattr(usage_metadata, "completion_tokens", 0),
                    )
                    total_tokens = getattr(usage_metadata, "total_tokens", None)
                    if total_tokens is None:
                        total_tokens = input_tokens + output_tokens

                return TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                )

            # Check if response has response_metadata attribute (BedrockChat format)
            elif hasattr(response, "response_metadata") and response.response_metadata:
                metadata = response.response_metadata
                if "usage" in metadata:
                    usage = metadata["usage"]
                    # Handle different token naming conventions
                    input_tokens = usage.get(
                        "input_tokens", usage.get("prompt_tokens", 0)
                    )
                    output_tokens = usage.get(
                        "output_tokens", usage.get("completion_tokens", 0)
                    )
                    total_tokens = usage.get("total_tokens")
                    if total_tokens is None:
                        total_tokens = input_tokens + output_tokens

                    return TokenUsage(
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        total_tokens=total_tokens,
                    )

            # Check if response has token_usage attribute
            elif hasattr(response, "token_usage") and response.token_usage:
                usage = response.token_usage
                # Handle different token naming conventions
                input_tokens = getattr(
                    usage, "input_tokens", getattr(usage, "prompt_tokens", 0)
                )
                output_tokens = getattr(
                    usage, "output_tokens", getattr(usage, "completion_tokens", 0)
                )
                total_tokens = getattr(usage, "total_tokens", None)
                if total_tokens is None:
                    total_tokens = input_tokens + output_tokens

                return TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                )

            logger.warning("No token usage information found in response")
            return None

        except Exception as e:
            logger.warning(f"Failed to extract token usage: {str(e)}")
            return None
