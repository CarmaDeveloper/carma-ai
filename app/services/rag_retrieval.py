"""RAG (Retrieval-Augmented Generation) retrieval service for chatbot."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage

from app.core.config import settings
from app.core.logging import setup_logger
from app.repositories import DocumentRecordRepositoryProtocol
from app.schemas.chatbot import DocumentReference
from app.services.vector_store import vector_store_service

logger = setup_logger(__name__)


@dataclass
class RAGContext:
    """Container for RAG retrieval results."""

    context_text: str
    documents: List[Document]
    references: List[DocumentReference]
    query_count: int
    knowledge_ids_searched: List[str] = field(default_factory=list)


class RAGRetrievalService:
    """Service for RAG document retrieval and context building."""

    def __init__(
        self,
        document_record_repo: DocumentRecordRepositoryProtocol,
    ) -> None:
        """
        Initialize RAG retrieval service.

        Args:
            document_record_repo: Repository for document records (for getting all knowledge IDs)
        """
        self._document_record_repo = document_record_repo
        self._vector_store = vector_store_service
        logger.info("RAG retrieval service initialized")

    async def retrieve_context(
        self,
        message: str,
        knowledge_id: Optional[str] = None,
        conversation_history: Optional[List[BaseMessage]] = None,
    ) -> RAGContext:
        """
        Retrieve relevant documents for RAG context.

        Args:
            message: Current user message to search for
            knowledge_id: Specific knowledge base ID. If None, searches ALL knowledge bases.
            conversation_history: Optional conversation history for additional queries

        Returns:
            RAGContext containing formatted context and document references
        """
        # Get configuration from settings
        config = self._get_config()

        # Build search queries
        queries = self._build_queries(
            current_message=message,
            history=conversation_history,
            include_history=config["include_history_queries"],
            max_history=config["max_history_queries"],
        )

        logger.info(
            f"RAG retrieval starting: knowledge_id={knowledge_id or 'ALL'}, "
            f"queries={len(queries)}, k={config['k']}"
        )

        # Retrieve documents
        if knowledge_id:
            # Search specific knowledge base
            documents = await self._search_single_knowledge_base(
                knowledge_id=knowledge_id,
                queries=queries,
                k=config["k"],
            )
            knowledge_ids_searched = [knowledge_id]
        else:
            # Search all knowledge bases
            documents, knowledge_ids_searched = await self._search_all_knowledge_bases(
                queries=queries,
                k=config["k"],
            )

        # Apply score threshold filtering if configured
        if config["score_threshold"] is not None:
            documents = self._filter_by_score(documents, config["score_threshold"])

        # Deduplicate documents
        documents = self._deduplicate_documents(documents)

        # Extract references before truncation
        references = self._extract_references(documents)

        # Format context with truncation
        context_text = self._format_context(
            documents=documents,
            max_length=config["max_context_length"],
        )

        logger.info(
            f"RAG retrieval completed: documents={len(documents)}, "
            f"references={len(references)}, context_length={len(context_text)}, "
            f"knowledge_bases_searched={len(knowledge_ids_searched)}"
        )

        return RAGContext(
            context_text=context_text,
            documents=documents,
            references=references,
            query_count=len(queries),
            knowledge_ids_searched=knowledge_ids_searched,
        )

    def _get_config(self) -> dict:
        """Get RAG configuration from settings."""
        return {
            "k": settings.RAG_DEFAULT_K,
            "score_threshold": settings.RAG_DEFAULT_SCORE_THRESHOLD,
            "include_history_queries": settings.RAG_INCLUDE_HISTORY_QUERIES,
            "max_history_queries": settings.RAG_MAX_HISTORY_QUERIES,
            "max_context_length": settings.RAG_MAX_CONTEXT_LENGTH,
        }

    def _build_queries(
        self,
        current_message: str,
        history: Optional[List[BaseMessage]] = None,
        include_history: bool = True,
        max_history: int = 2,
    ) -> List[str]:
        """
        Build search queries from message and optional conversation history.

        Strategy:
        1. Primary query: Current user message (always included)
        2. Secondary queries: Last N human messages from history (if enabled)

        Args:
            current_message: The current user message
            history: Conversation history (list of BaseMessage)
            include_history: Whether to include history in queries
            max_history: Maximum number of history messages to use

        Returns:
            List of query strings for similarity search
        """
        queries = [current_message]

        if include_history and history and max_history > 0:
            # Extract recent human messages from history (excluding current message)
            # History is in chronological order, so we reverse to get most recent first
            human_messages = [
                msg.content
                for msg in reversed(history)
                if isinstance(msg, HumanMessage) and msg.content != current_message
            ][:max_history]

            queries.extend(human_messages)
            logger.debug(
                f"Built {len(queries)} queries: 1 current + {len(human_messages)} from history"
            )

        return queries

    async def _search_single_knowledge_base(
        self,
        knowledge_id: str,
        queries: List[str],
        k: int,
    ) -> List[Document]:
        """Search a single knowledge base."""
        try:
            documents = await self._vector_store.similarity_search(
                knowledge_id=knowledge_id,
                queries=queries,
                k=k,
            )
            return documents
        except Exception as e:
            logger.warning(
                f"Failed to search knowledge base {knowledge_id}: {e}. "
                "Continuing without this knowledge base."
            )
            return []

    async def _search_all_knowledge_bases(
        self,
        queries: List[str],
        k: int,
    ) -> Tuple[List[Document], List[str]]:
        """
        Search across all available knowledge bases.

        Args:
            queries: Search queries
            k: Number of documents per query per knowledge base

        Returns:
            Tuple of (combined documents, list of knowledge IDs searched)
        """
        # Get all knowledge base IDs
        knowledge_ids = await self._document_record_repo.get_all_knowledge_ids()

        if not knowledge_ids:
            logger.warning("No knowledge bases found for RAG search")
            return [], []

        logger.info(
            f"Searching across {len(knowledge_ids)} knowledge bases: {knowledge_ids}"
        )

        all_documents: List[Document] = []
        searched_ids: List[str] = []

        for kb_id in knowledge_ids:
            try:
                docs = await self._vector_store.similarity_search(
                    knowledge_id=kb_id,
                    queries=queries,
                    k=k,
                )
                all_documents.extend(docs)
                searched_ids.append(kb_id)
                logger.debug(
                    f"Retrieved {len(docs)} documents from knowledge base: {kb_id}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to search knowledge base {kb_id}: {e}. "
                    "Continuing with other knowledge bases."
                )

        return all_documents, searched_ids

    def _filter_by_score(
        self,
        documents: List[Document],
        threshold: float,
    ) -> List[Document]:
        """
        Filter documents by relevance score threshold.

        Note: This requires documents to have a 'score' in metadata.
        If score is not available, documents are kept.
        """
        original_count = len(documents)
        filtered = []

        for doc in documents:
            score = doc.metadata.get("score")
            if score is None or score >= threshold:
                filtered.append(doc)

        if len(filtered) < original_count:
            logger.info(
                f"Score filtering: {original_count} → {len(filtered)} documents "
                f"(threshold={threshold})"
            )

        return filtered

    def _deduplicate_documents(self, documents: List[Document]) -> List[Document]:
        """Remove duplicate documents based on content hash."""
        unique_docs = []
        seen_content = set()

        for doc in documents:
            content_hash = hash(doc.page_content)
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_docs.append(doc)

        if len(unique_docs) < len(documents):
            logger.debug(
                f"Deduplication: {len(documents)} → {len(unique_docs)} documents"
            )

        return unique_docs

    def _extract_references(self, documents: List[Document]) -> List[DocumentReference]:
        """
        Extract document references from retrieved documents.

        Args:
            documents: List of retrieved documents

        Returns:
            List of DocumentReference objects
        """
        references = []
        seen_doc_ids = set()

        for doc in documents:
            doc_id = doc.metadata.get("document_id", "")
            if not doc_id or doc_id in seen_doc_ids:
                continue

            seen_doc_ids.add(doc_id)

            reference = DocumentReference(
                document_id=doc_id,
                file_name=doc.metadata.get("file_name", "Unknown"),
                knowledge_id=doc.metadata.get("knowledge_id", "Unknown"),
                source_url=doc.metadata.get("source_s3_url"),
                relevance_score=doc.metadata.get("score"),
            )
            references.append(reference)

        return references

    def _format_context(
        self,
        documents: List[Document],
        max_length: int,
    ) -> str:
        """
        Format retrieved documents as context string with truncation.

        Truncation strategy:
        1. Documents are assumed to be sorted by relevance
        2. Add documents until max_length is reached
        3. If a single document is too long, truncate it
        4. Always include at least one document (even if truncated)

        Args:
            documents: List of retrieved documents
            max_length: Maximum character length for context

        Returns:
            Formatted context string
        """
        if not documents:
            return ""

        context_parts = []
        current_length = 0
        truncated = False
        separator = "\n\n---\n\n"
        separator_length = len(separator)

        for i, doc in enumerate(documents):
            doc_text = self._format_single_document(doc, i + 1)
            doc_length = len(doc_text)

            # Check if we can add this document
            projected_length = current_length + doc_length
            if context_parts:
                projected_length += separator_length

            if projected_length <= max_length:
                context_parts.append(doc_text)
                current_length = projected_length
            elif i == 0:
                # First document - must include, truncate if needed
                available = max_length - 50  # Reserve space for truncation notice
                truncated_text = doc_text[:available] + "\n[... content truncated ...]"
                context_parts.append(truncated_text)
                truncated = True
                break
            else:
                # Skip remaining documents
                truncated = True
                break

        if truncated:
            logger.info(
                f"Context truncated: included {len(context_parts)} of {len(documents)} documents"
            )

        return separator.join(context_parts)

    def _format_single_document(self, doc: Document, index: int) -> str:
        """
        Format a single document for context.

        Args:
            doc: Document to format
            index: Document index (1-based)

        Returns:
            Formatted document string
        """
        # Extract metadata for source attribution
        file_name = doc.metadata.get("file_name", "Unknown Source")
        knowledge_id = doc.metadata.get("knowledge_id", "")

        source_info = f"Source: {file_name}"
        if knowledge_id:
            source_info += f" (Knowledge Base: {knowledge_id})"

        return f"**Document {index}** - {source_info}\n\n{doc.page_content}"
