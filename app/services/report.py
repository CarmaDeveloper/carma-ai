"""Report generation service."""

from typing import Dict, List, Set, Optional

from langchain_core.documents import Document

from app.core.exceptions import ModelError
from app.core.logging import setup_logger
from app.models.report import (
    QAItem,
    ReportGenerationRequest,
    ReportGenerationResponse,
    TokenUsage,
)
from app.prompts.report import (
    RAG_PROMPT_TEMPLATE,
    NO_CONTEXT_PROMPT_TEMPLATE,
    effective_prompt as compute_effective_prompt,
)
from app.services.comprehend import comprehend_service
from app.services.model import model_service
from app.services.vector_store import vector_store_service

logger = setup_logger(__name__)


class ReportGenerationService:
    """Service for generating reports using RAG."""

    async def generate_report(
        self, request: ReportGenerationRequest
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
        scores = request.get_scores()
        logger.info(
            f"Starting report generation: knowledge_id={request.knowledge_id}, "
            f"qa_count={len(request.qas)}, prompt_length={len(request.prompt)}, "
            f"scores={scores}"
        )

        try:
            # Step 1: Process answers through Comprehend for PII redaction
            answers = [qa.answer for qa in request.qas]
            redacted_answers = await comprehend_service.redact_pii(answers)

            logger.info(
                f"Completed PII redaction: redacted_count={len(redacted_answers)}"
            )
            logger.info(f"Redacted answers: {redacted_answers}")

            # Step 2: Get context from vector store if knowledge_id provided
            context_docs = []
            if request.knowledge_id:
                context_docs = await self._get_context(
                    request.knowledge_id, request.qas
                )
                logger.info(f"Retrieved context: doc_count={len(context_docs)}")

            # Step 3: Get references from context
            references = self._extract_references(context_docs)

            # Step 4: Get document IDs from context
            document_ids = self._extract_document_ids(context_docs)
            logger.info(
                f"Extracted document IDs: doc_id_count={len(document_ids)}, ids={list(document_ids)}"
            )

            # Step 5: Generate report with direct model call to capture token usage
            qa_text = self._format_qas(request.qas, redacted_answers)

            # Format scores for inclusion in prompt
            scores_text = self._format_scores(scores)

            # Log the full request before sending to Bedrock
            self._log_bedrock_request(request, qa_text, context_docs, scores_text)

            # Use direct model call to capture token usage
            message, token_usage = await self._generate_with_token_tracking(
                request.prompt, context_docs, qa_text, scores_text
            )

            logger.info(f"Generated report: message_length={len(message)}")
            logger.info(f"Message: {message}")
            if token_usage:
                logger.info(
                    f"Token usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}"
                )

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

    async def _get_context(
        self, knowledge_id: str, qas: List[QAItem]
    ) -> List[Document]:
        """Retrieve context documents from vector store."""
        try:
            # Extract questions for similarity search
            questions = [qa.question for qa in qas]

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
        self, user_prompt, context_docs, qa_text, scores_text
    ) -> tuple[str, Optional[TokenUsage]]:
        """Generate report with direct model call to capture token usage."""
        try:
            model = model_service.get_model()
            logger.info(f"Model: {model}")
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

            # Make direct model call to capture token usage
            response = await model.ainvoke(formatted_prompt)

            # Extract message and token usage
            message = (
                response.content if hasattr(response, "content") else str(response)
            )
            token_usage = self._extract_token_usage(response)

            return message, token_usage

        except Exception as e:
            logger.error(f"Failed to generate report with token tracking: {str(e)}")
            raise ModelError(f"Failed to generate report: {str(e)}")

    def _format_qas(self, qas: List[QAItem], redacted_answers: List[str]) -> str:
        """Format question-answer pairs for the prompt."""
        formatted_qas = []

        for i, qa in enumerate(qas):
            answer = redacted_answers[i] if i < len(redacted_answers) else qa.answer
            formatted_qas.append(f"Question: {qa.question}\nAnswer: {answer}")

        return "\n\n".join(formatted_qas)

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
            if doc.metadata and "source" in doc.metadata:
                source_path = doc.metadata["source"]
                # Extract filename from path
                filename = (
                    source_path.split("/")[-1] if "/" in source_path else source_path
                )
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


# Singleton instance
report_service = ReportGenerationService()
