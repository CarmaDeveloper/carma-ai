"""Chatbot service with database-backed session management and optional RAG."""

import json
import uuid
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any, Optional, Tuple
from uuid import UUID

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage

from app.core.config import settings
from app.core.logging import setup_logger
from app.repositories import (
    SessionRepositoryProtocol,
    MessageRepositoryProtocol,
    DocumentRecordRepositoryProtocol,
)
from app.prompts.chatbot import build_system_prompt
from app.schemas.chatbot import DocumentReference
from app.services.model import model_service
from app.services.rag_retrieval import RAGRetrievalService

logger = setup_logger(__name__)


class ChatbotService:
    """Service to handle conversational chat with database-backed session management and optional RAG."""

    def __init__(
        self,
        session_repo: SessionRepositoryProtocol,
        message_repo: MessageRepositoryProtocol,
        document_record_repo: DocumentRecordRepositoryProtocol,
    ):
        """
        Initialize the chatbot service with database persistence and RAG.

        Args:
            session_repo: Session repository (required for dependency injection)
            message_repo: Message repository (required for dependency injection)
            document_record_repo: Document record repository for RAG (required)
        """
        # Load session configuration from settings
        self.message_history_limit = settings.CHATBOT_MESSAGE_HISTORY_LIMIT

        # Store repositories
        self._session_repo = session_repo
        self._message_repo = message_repo

        # Create RAG service
        self._rag_service = RAGRetrievalService(
            document_record_repo=document_record_repo
        )

        logger.info("Chatbot service initialized with database persistence and RAG")

    def _generate_id(self) -> str:
        """Generate a unique UUID."""
        return str(uuid.uuid4())

    async def _load_conversation_history(self, session_id: str) -> List[BaseMessage]:
        """
        Load conversation history from database in chronological order.

        Args:
            session_id: Session identifier

        Returns:
            List of LangChain messages (HumanMessage and AIMessage) in chronological order
        """
        try:
            # Request messages in chronological order (ASC) so LangChain receives proper context
            message_models, _ = await self._message_repo.get_by_session(
                session_id=UUID(session_id),
                page=1,
                per_page=self.message_history_limit,
                order="ASC",
            )

            messages = []
            for msg_model in message_models:
                if msg_model.message_type == "human":
                    messages.append(HumanMessage(content=msg_model.content))
                elif msg_model.message_type == "ai":
                    messages.append(AIMessage(content=msg_model.content))

            logger.debug(
                f"Loaded {len(messages)} messages from history for session {session_id}"
            )
            return messages

        except Exception as e:
            logger.error(f"Error loading conversation history: {e}", exc_info=True)
            return []

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a session by ID.

        Args:
            session_id: Session identifier (UUID string)

        Returns:
            Dictionary with session data, or None if not found
        """
        try:
            session_model = await self._session_repo.get_by_id(UUID(session_id))
            if session_model:
                return session_model.to_dict()
            return None
        except Exception as e:
            logger.error(f"Error getting session: {e}", exc_info=True)
            return None

    async def get_session_stats(self) -> Dict[str, Any]:
        """
        Get statistics about chatbot sessions.

        Returns:
            Dictionary with session and message statistics
        """
        try:
            return await self._session_repo.get_stats()
        except Exception as e:
            logger.error(f"Error getting session stats: {e}", exc_info=True)
            return {
                "sessions": {"total": 0, "active": 0, "inactive": 0, "unique_users": 0},
                "messages": {"total": 0, "human": 0, "ai": 0, "avg_per_session": 0},
            }

    async def stream_chat(
        self,
        *,
        message: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        use_rag: bool = True,
        knowledge_id: Optional[str] = None,
    ) -> AsyncGenerator[tuple[str, dict], None]:
        """
        Stream a chat response with database-backed session management and optional RAG.

        This method:
        1. Creates a new session or loads existing session from database
        2. Loads conversation history from database
        3. Saves user message to database
        4. If RAG is enabled, retrieves relevant context from knowledge base(s)
        5. Streams AI response with context-aware prompt
        6. Saves AI response to database with RAG metadata

        Args:
            message: The user's input message
            session_id: Optional session ID for conversation continuity
            user_id: Optional user identifier
            metadata: Optional session metadata
            use_rag: Whether to use RAG for context retrieval (default: True)
            knowledge_id: Knowledge base ID for RAG. If None and use_rag=True, searches all knowledge bases.

        Yields:
            Tuples of (event_type, data_dict) where:
            - First yield: ("chatbot.session", {"session_id": "...", "is_new": bool, "message_id": "...", "message_created_at": "...", "references": [...], "document_count": N})
            - Subsequent yields: ("chatbot.chunk", {"content": "chunk"})
            - Final yield: ("chatbot.complete", {"status": "complete", "message_count": N})

        Raises:
            Exception: Any underlying model or database error
        """
        # Determine if this is a new session
        is_new_session = session_id is None

        # Generate or validate session ID
        if is_new_session:
            session_id = self._generate_id()
            logger.info(f"Generated new session ID: {session_id}")

            # Generate title from first 50 characters of first message
            title = message[:50] if message else None

            # Create session in database
            try:
                await self._session_repo.create(
                    session_id=UUID(session_id),
                    user_id=user_id,
                    title=title,
                    metadata=metadata or {},
                )
                logger.info(
                    f"Created new session in database: {session_id} with title: {title}"
                )
            except Exception as e:
                logger.error(f"Error creating session: {e}", exc_info=True)
                yield (
                    "chatbot.error",
                    {"error": str(e), "message": "Failed to create session"},
                )
                return
        else:
            logger.info(f"Using existing session ID: {session_id}")

            # Update last accessed time (session validation is handled by API layer)
            try:
                await self._session_repo.update_access_time(UUID(session_id))
            except Exception as e:
                logger.error(f"Error updating session access time: {e}", exc_info=True)
                # Don't fail the request if access time update fails, just log it

        # Load conversation history from database
        try:
            history_messages = await self._load_conversation_history(session_id)
            logger.info(
                f"Loaded {len(history_messages)} messages from history for session {session_id}"
            )
        except Exception as e:
            logger.error(f"Error loading history: {e}", exc_info=True)
            history_messages = []

        # Save user message to database
        try:
            await self._message_repo.create(
                message_id=UUID(self._generate_id()),
                session_id=UUID(session_id),
                message_type="human",
                content=message,
                metadata=metadata or {},
            )
            logger.debug(f"Saved user message to database for session {session_id}")
        except Exception as e:
            logger.error(f"Error saving user message: {e}", exc_info=True)
            yield (
                "chatbot.error",
                {"error": str(e), "message": "Failed to save user message"},
            )
            return

        # Add current user message to history for model context
        history_messages.append(HumanMessage(content=message))

        # RAG context retrieval (before session event so we can include references)
        rag_context = None
        rag_references: List[DocumentReference] = []
        rag_document_ids: List[str] = []

        if use_rag:
            try:
                logger.info(
                    f"RAG enabled: retrieving context for session {session_id}, "
                    f"knowledge_id={knowledge_id or 'ALL'}"
                )
                rag_context = await self._rag_service.retrieve_context(
                    message=message,
                    knowledge_id=knowledge_id,
                    conversation_history=history_messages[
                        :-1
                    ],  # Exclude current message
                )

                rag_references = rag_context.references
                rag_document_ids = [ref.document_id for ref in rag_references]

                logger.info(
                    f"RAG context retrieved: {len(rag_context.documents)} documents, "
                    f"{len(rag_references)} unique references"
                )
            except Exception as e:
                logger.warning(
                    f"RAG retrieval failed, continuing without context: {e}",
                    exc_info=True,
                )
                # Continue without RAG context on failure
                rag_context = None

        # Pre-generate AI message ID and timestamp for the session event
        ai_message_id = self._generate_id()
        ai_message_created_at = datetime.now().isoformat()

        # Yield session information with AI response message ID, created_at, and RAG references
        session_event_data: Dict[str, Any] = {
            "session_id": session_id,
            "is_new": is_new_session,
            "message_id": ai_message_id,
            "message_created_at": ai_message_created_at,
        }

        # Include RAG references in session event (just source URLs)
        if rag_context:
            session_event_data["references"] = [
                ref.source_url for ref in rag_references if ref.source_url
            ]
            session_event_data["document_count"] = len(rag_context.documents)
            session_event_data["knowledge_ids_searched"] = (
                rag_context.knowledge_ids_searched
            )

        yield ("chatbot.session", session_event_data)

        # Build system prompt with optional RAG context
        context_text = rag_context.context_text if rag_context else None
        system_prompt = build_system_prompt(context=context_text)

        # Build messages for the model (system message + conversation history)
        messages_for_model = [SystemMessage(content=system_prompt)] + history_messages
        logger.info(
            f"Sending {len(messages_for_model)} messages to model "
            f"(1 system + {len(history_messages)} history, RAG: {rag_context is not None})"
        )

        # Get model and stream response
        try:
            model = model_service.get_model()
            full_response = ""

            # Variables to capture token usage
            input_tokens = 0
            output_tokens = 0
            total_tokens = 0

            # Stream the AI response with full conversation history
            async for chunk in model.astream(messages_for_model):
                content = getattr(chunk, "content", None)

                # Only process chunks with actual content (skip empty metadata chunks)
                if content and isinstance(content, str) and len(content.strip()) > 0:
                    full_response += content
                    yield ("chatbot.chunk", {"content": content})

                # Capture token usage from usage_metadata if available
                usage_metadata = getattr(chunk, "usage_metadata", None)
                if usage_metadata:
                    input_tokens = usage_metadata.get("input_tokens", 0)
                    output_tokens = usage_metadata.get("output_tokens", 0)
                    total_tokens = usage_metadata.get("total_tokens", 0)
                    logger.info(
                        f"Token usage - Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}"
                    )

            # Build message metadata including RAG info
            ai_message_metadata: Dict[str, Any] = {
                "model": getattr(model, "model_id", "unknown"),
                **(metadata or {}),
            }

            # Add RAG metadata if context was used
            if rag_context:
                ai_message_metadata["rag"] = {
                    "enabled": True,
                    "knowledge_id": knowledge_id,
                    "knowledge_ids_searched": rag_context.knowledge_ids_searched,
                    "document_ids": rag_document_ids,
                    "references": [ref.file_name for ref in rag_references],
                    "query_count": rag_context.query_count,
                    "context_length": len(rag_context.context_text),
                }

            # Save AI response to database with pre-generated message ID
            try:
                await self._message_repo.create(
                    message_id=UUID(ai_message_id),
                    session_id=UUID(session_id),
                    message_type="ai",
                    content=full_response,
                    metadata=ai_message_metadata,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                )
                logger.debug(f"Saved AI response to database for session {session_id}")
            except Exception as e:
                logger.error(f"Error saving AI response: {e}", exc_info=True)
                yield (
                    "chatbot.error",
                    {"error": str(e), "message": "Failed to save AI response"},
                )

            # Get current message count
            try:
                message_count = await self._message_repo.get_count_by_session(
                    UUID(session_id)
                )
            except Exception as e:
                logger.error(f"Error getting message count: {e}", exc_info=True)
                message_count = 0

            # Signal end of stream
            yield (
                "chatbot.complete",
                {"status": "complete", "message_count": message_count},
            )

        except Exception as e:
            logger.error(f"Chatbot streaming failed: {e}", exc_info=True)
            yield (
                "chatbot.error",
                {"error": str(e), "message": "Failed to stream chat response"},
            )

    def format_sse_event(self, event_type: str, data: dict) -> str:
        """
        Format data as Server-Sent Event with JSON payload.

        Args:
            event_type: Type of the event (chatbot.session, chatbot.chunk, chatbot.complete, chatbot.error)
            data: Dictionary data to send as JSON

        Returns:
            Formatted SSE string with JSON data
        """
        json_data = json.dumps(data)
        return f"event: {event_type}\ndata: {json_data}\n\n"

    async def get_session_messages(
        self, session_id: str, page: int = 1, per_page: int = 50, order: str = "ASC"
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Get messages for a session with pagination.

        Args:
            session_id: Session identifier (UUID string)
            page: Page number (1-indexed)
            per_page: Number of messages per page
            order: Sort order ("ASC" or "DESC")

        Returns:
            Tuple of (list of message dictionaries, pagination metadata)
        """
        try:
            message_models, pagination_metadata = (
                await self._message_repo.get_by_session(
                    session_id=UUID(session_id),
                    page=page,
                    per_page=per_page,
                    order=order,
                )
            )
            return (
                [msg_model.to_dict() for msg_model in message_models],
                pagination_metadata,
            )
        except Exception as e:
            logger.error(f"Error getting session messages: {e}", exc_info=True)
            return [], {}

    async def get_user_sessions(
        self, user_id: str, active_only: bool = True, page: int = 1, per_page: int = 50
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Get sessions for a user with pagination.

        Args:
            user_id: User identifier
            active_only: Whether to return only active sessions
            page: Page number (1-indexed)
            per_page: Number of sessions per page

        Returns:
            Tuple of (list of session dictionaries, pagination metadata)
        """
        try:
            session_models, pagination_metadata = (
                await self._session_repo.get_user_sessions(
                    user_id, active_only, page, per_page
                )
            )
            return (
                [session_model.to_dict() for session_model in session_models],
                pagination_metadata,
            )
        except Exception as e:
            logger.error(f"Error getting user sessions: {e}", exc_info=True)
            return [], {}

    async def get_user_sessions_count(
        self, user_id: str, active_only: bool = True
    ) -> int:
        """
        Get the total count of sessions for a user.

        Args:
            user_id: User identifier (UUID string)
        """
        return await self._session_repo.get_user_sessions_count(user_id, active_only)

    async def delete_session_permanently(self, session_id: str) -> bool:
        """
        Delete a session permanently.

        Args:
            session_id: Session identifier (UUID string)

        Returns:
            True if session was deleted, False if session not found
        """
        try:
            session_model = await self._session_repo.get_by_id(UUID(session_id))
            if not session_model:
                return False
            return await self._session_repo.delete_permanently(session_model)
        except Exception as e:
            logger.error(f"Error deleting session permanently: {e}", exc_info=True)
            return False

    async def delete_old_sessions(self, retention_days: int) -> int:
        """
        Delete old sessions.

        Args:
            retention_days: Retention days
        """
        return await self._session_repo.delete_old_sessions(retention_days)

    async def deactivate_session(self, session_id: str) -> bool:
        """
        Deactivate a session.

        Args:
            session_id: Session identifier (UUID string)

        Returns:
            True if session was deactivated, False if session not found
        """
        try:
            session_model = await self._session_repo.get_by_id(UUID(session_id))
            if not session_model:
                return False
            return await self._session_repo.deactivate(session_model)
        except Exception as e:
            logger.error(f"Error deactivating session: {e}", exc_info=True)
            return False

    async def add_message_reaction(
        self, message_id: str, session_id: str, reaction_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Add a reaction to a message.

        Args:
            message_id: Message identifier (UUID string)
            session_id: Session identifier (UUID string)
            reaction_type: Reaction type (LIKE or DISLIKE)

        Returns:
            Dictionary with message data including reaction, or None if message not found
        """
        try:
            message_model = await self._message_repo.get_by_id(
                UUID(message_id), UUID(session_id)
            )
            if not message_model:
                return None
            updated_message = await self._message_repo.add_reaction(
                message_model, reaction_type
            )
            if updated_message:
                return updated_message.to_dict()
            return None
        except Exception as e:
            logger.error(f"Error adding message reaction: {e}", exc_info=True)
            return None
