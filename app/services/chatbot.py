"""Chatbot service with session management using LangGraph and LangChain."""

import asyncio
import json
import time
import uuid
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, MessagesState, StateGraph

from app.core.config import settings
from app.core.logging import setup_logger
from app.prompts.chatbot import CHATBOT_SYSTEM_PROMPT
from app.services.model import model_service

logger = setup_logger(__name__)


class ChatbotService:
    """Service to handle conversational chat with session management."""

    def __init__(self):
        """Initialize the chatbot service with LangGraph workflow."""
        self.memory = MemorySaver()
        self.app = None

        # Load session configuration from settings
        self.session_ttl_seconds = settings.CHATBOT_SESSION_TTL_SECONDS
        self.max_sessions = settings.CHATBOT_MAX_SESSIONS
        self.cleanup_interval_seconds = settings.CHATBOT_CLEANUP_INTERVAL_SECONDS

        # Track session access times for cleanup
        self._session_last_access: dict[str, float] = {}
        self._session_lock = asyncio.Lock()
        self._cleanup_task = None

        self._initialize_workflow()

    def _initialize_workflow(self):
        """Initialize the LangGraph workflow with memory."""
        # Create a prompt template
        prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", CHATBOT_SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        # Define the workflow
        workflow = StateGraph(state_schema=MessagesState)

        async def call_model(state: MessagesState):
            """Call the model with the current state."""
            # Get the LangChain-compatible model
            model = model_service.get_model()

            # Format prompt with messages
            prompt = prompt_template.invoke(state)

            # Invoke model
            response = await model.ainvoke(prompt)

            # Return the response as a message
            return {"messages": [response]}

        # Add node and edge
        workflow.add_edge(START, "model")
        workflow.add_node("model", call_model)

        # Compile with memory checkpointer
        self.app = workflow.compile(checkpointer=self.memory)

        logger.info("LangGraph workflow initialized with memory")

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        return str(uuid.uuid4())

    async def startup(self):
        """Start the background cleanup task on application startup."""
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info(
            f"Started session cleanup task (TTL: {self.session_ttl_seconds}s, "
            f"Interval: {self.cleanup_interval_seconds}s, Max: {self.max_sessions})"
        )

    async def shutdown(self):
        """Stop the background cleanup task on application shutdown."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped session cleanup task")

    async def _periodic_cleanup(self):
        """Periodically clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                logger.info("Cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}", exc_info=True)

    async def _cleanup_expired_sessions(self):
        """Remove expired sessions from memory."""
        current_time = time.time()
        expired_sessions = []

        # Find expired sessions (protected by lock)
        async with self._session_lock:
            for session_id, last_access in self._session_last_access.items():
                if current_time - last_access > self.session_ttl_seconds:
                    expired_sessions.append(session_id)

        # Remove expired sessions
        for session_id in expired_sessions:
            try:
                # Remove from MemorySaver storage
                thread_id = {"configurable": {"thread_id": session_id}}
                # MemorySaver stores checkpoints - we need to clear them
                if hasattr(self.memory, "storage"):
                    # Remove from internal storage
                    keys_to_remove = [
                        k for k in self.memory.storage if k[0] == session_id
                    ]
                    for key in keys_to_remove:
                        del self.memory.storage[key]

                # Remove from tracking (protected by lock)
                async with self._session_lock:
                    del self._session_last_access[session_id]
                logger.info(f"Cleaned up expired session: {session_id}")
            except Exception as e:
                logger.error(f"Error cleaning up session {session_id}: {e}")

        if expired_sessions:
            async with self._session_lock:
                active_count = len(self._session_last_access)
            logger.info(
                f"Cleaned up {len(expired_sessions)} expired sessions. "
                f"Active sessions: {active_count}"
            )

        # Also enforce max sessions limit
        await self._enforce_session_limit()

    async def _enforce_session_limit(self):
        """Enforce maximum session limit by removing oldest sessions."""
        sessions_to_remove = []
        num_to_remove = 0
        sessions_copy = {}
        async with self._session_lock:
            # Quickly get a copy of sessions under lock
            sessions_copy = self._session_last_access.copy()
        if len(sessions_copy) > self.max_sessions:
            # Sort by access time and find oldest sessions to remove (outside the lock)
            sorted_sessions = sorted(sessions_copy.items(), key=lambda x: x[1])
            num_to_remove = len(sessions_copy) - self.max_sessions
            sessions_to_remove = [s[0] for s in sorted_sessions[:num_to_remove]]

        # Remove sessions outside the lock to avoid holding it too long
        for session_id in sessions_to_remove:
            try:
                # Remove from MemorySaver storage
                if hasattr(self.memory, "storage"):
                    keys_to_remove = [
                        k for k in self.memory.storage if k[0] == session_id
                    ]
                    for key in keys_to_remove:
                        del self.memory.storage[key]

                # Remove from tracking (protected by lock)
                async with self._session_lock:
                    if session_id in self._session_last_access:
                        del self._session_last_access[session_id]
                logger.info(f"Removed session due to limit: {session_id}")
            except Exception as e:
                logger.error(f"Error removing session {session_id}: {e}")

        if sessions_to_remove:
            logger.warning(
                f"Enforced session limit: removed {num_to_remove} oldest sessions"
            )

    async def _track_session_access(self, session_id: str):
        """Track that a session was accessed."""
        async with self._session_lock:
            self._session_last_access[session_id] = time.time()

    async def get_session_stats(self) -> dict:
        """Get statistics about active sessions."""
        current_time = time.time()
        active_count = 0

        async with self._session_lock:
            for last_access in self._session_last_access.values():
                if current_time - last_access <= self.session_ttl_seconds:
                    active_count += 1

            return {
                "total_sessions": len(self._session_last_access),
                "active_sessions": active_count,
                "max_sessions": self.max_sessions,
                "session_ttl_seconds": self.session_ttl_seconds,
            }

    async def stream_chat(
        self, *, message: str, session_id: str | None = None
    ) -> AsyncGenerator[tuple[str, dict], None]:
        """
        Stream a chat response with session management.

        This method maintains conversation history using LangGraph's persistence.
        If no session_id is provided, a new one is generated.

        Args:
            message: The user's input message.
            session_id: Optional session ID for conversation continuity.

        Yields:
            Tuples of (event_type, data_dict) where:
            - First yield: ("chatbot.session", {"session_id": "...", "is_new": bool})
            - Subsequent yields: ("chatbot.chunk", {"content": "chunk"})
            - Final yield: ("chatbot.complete", {"status": "complete"})

        Raises:
            Exception: Any underlying model or streaming error.
        """
        # Generate or use existing session ID
        is_new_session = session_id is None
        if session_id is None:
            session_id = self._generate_session_id()
            logger.info(f"Generated new session ID: {session_id}")
        else:
            logger.info(f"Using existing session ID: {session_id}")

        # Track session access for cleanup
        await self._track_session_access(session_id)

        # Yield the session ID first with metadata
        yield ("chatbot.session", {"session_id": session_id, "is_new": is_new_session})

        # Create config with thread_id for session management
        config = {"configurable": {"thread_id": session_id}}

        # Create input messages
        input_messages = [HumanMessage(content=message)]

        try:
            # Stream the response from LangGraph
            async for chunk, metadata in self.app.astream(
                {"messages": input_messages},
                config,
                stream_mode="messages",
            ):
                # Filter to only AIMessage chunks
                if isinstance(chunk, AIMessage):
                    content = chunk.content
                    if content:
                        yield ("chatbot.chunk", {"content": content})

            # Signal end of stream
            yield ("chatbot.complete", {"status": "complete"})

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
            event_type: Type of the event (chatbot.session, chatbot.chunk, chatbot.complete, chatbot.error).
            data: Dictionary data to send as JSON.

        Returns:
            Formatted SSE string with JSON data.
        """
        json_data = json.dumps(data)
        return f"event: {event_type}\ndata: {json_data}\n\n"


# Singleton instance
chatbot_service = ChatbotService()
