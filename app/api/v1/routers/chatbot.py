"""Chatbot API endpoints with database-backed session management."""

import asyncio

from fastapi import APIRouter, HTTPException, Query, Depends, status
from fastapi.responses import StreamingResponse

from app.core.auth import get_user_id
from app.core.logging import setup_logger
from app.dependencies.get_chatbot_service import get_chatbot_service
from app.schemas.chatbot import (
    ChatbotRequest,
    SessionHistoryResponse,
    SessionListResponse,
    SessionStatsResponse,
    DeleteSessionResponse,
    MessageResponse,
    SessionResponse,
    AddMessageReactionRequest,
    MessageReactionResponse,
    ReactionType,
    PaginationMetadata,
)
from app.services.chatbot import ChatbotService

logger = setup_logger(__name__)

router = APIRouter(tags=["chatbot"], prefix="/chatbot")


async def verify_session_access(
    session_id: str,
    user_id: str,
    chatbot_service: ChatbotService,
    require_active: bool = True,
) -> dict:
    """
    Shared helper function to verify session access, ownership, and active status.

    This function centralizes session validation logic used across multiple endpoints:
    1. Fetches the session from the database
    2. Verifies the session exists (404 if not found)
    3. Verifies the user owns the session (403 if unauthorized)
    4. Optionally verifies the session is active (400 if inactive)

    Args:
        session_id: Session identifier to verify
        user_id: User identifier (should be obtained from get_user_id dependency)
        chatbot_service: ChatbotService instance (injected via dependency)
        require_active: Whether to require the session to be active (default: True)

    Returns:
        dict: Session data dictionary

    Raises:
        HTTPException:
            - 404: Session not found
            - 403: User not authorized to access this session
            - 400: Session is inactive (if require_active=True)
    """
    session = await chatbot_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Authorization check: user must own the session
    if session.get("user_id") and session["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this session",
        )

    # Check if session is active (if required)
    if require_active and not session.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session {session_id} is inactive",
        )

    return session


@router.post(
    "/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream chatbot conversation via Server-Sent Events with RAG support",
)
async def stream_chatbot(
    request: ChatbotRequest,
    user_id: str = Depends(get_user_id),
    chatbot_service: ChatbotService = Depends(get_chatbot_service),
) -> StreamingResponse:
    """
    Stream chatbot responses using Server-Sent Events (SSE) with RAG-enhanced responses.

    This endpoint:
    1. Creates a new session or uses existing session (stored in database)
    2. Loads conversation history from database
    3. Saves user message to database
    4. If RAG enabled, retrieves relevant documents from knowledge base(s)
    5. Streams AI response as SSE events (with context-aware prompt if RAG enabled)
    6. Saves AI response to database with RAG metadata
    7. Emits completion event with message count and document references

    **RAG (Retrieval-Augmented Generation):**
    - `use_rag`: Enable/disable RAG (default: True)
    - `knowledge_id`: Specific knowledge base to search. If None, searches ALL knowledge bases.
    - RAG configuration (k, score_threshold, etc.) is controlled via server settings.

    **SSE Event Types (all data is JSON):**
    - `chatbot.session`: `{"session_id": "...", "is_new": true/false, "message_id": "...", "message_created_at": "...", "references": ["s3://..."], "document_count": N, "knowledge_ids_searched": [...]}` (references as S3 URLs if RAG enabled)
    - `chatbot.chunk`: `{"content": "chunk of text"}`
    - `chatbot.complete`: `{"status": "complete", "message_count": N}`
    - `chatbot.error`: `{"error": "error message", "message": "description"}`

    **Authentication:**
    - Requires `User-Id` header with a valid user identifier

    Args:
        request: ChatbotRequest containing message, optional session_id, metadata, and RAG configuration
        user_id: User identifier from User-Id header (required)

    Returns:
        StreamingResponse: SSE stream with media type `text/event-stream`

    Raises:
        HTTPException:
            - 400: Missing or invalid User-Id header
            - 403: User not authorized to access the requested session
            - 500: On server errors before streaming begins
        Errors during streaming are sent within the SSE stream as error events
    """
    try:
        # Authorization check for existing sessions
        if request.session_id:
            # Verify session access, ownership, and active status
            await verify_session_access(
                session_id=request.session_id,
                user_id=user_id,
                chatbot_service=chatbot_service,
                require_active=True,
            )

        # Determine effective use_rag value (defaults to True if not specified)
        use_rag = request.use_rag is not False

        async def event_generator():
            """Generate SSE events from the chatbot service."""
            try:
                async for event_type, data in chatbot_service.stream_chat(
                    message=request.message,
                    session_id=request.session_id,
                    user_id=user_id,
                    metadata=request.metadata,
                    use_rag=use_rag,
                    knowledge_id=request.knowledge_id,
                ):
                    # Format as SSE event with JSON data
                    sse_message = chatbot_service.format_sse_event(event_type, data)
                    yield sse_message
            except asyncio.CancelledError:
                logger.info(
                    "Client disconnected from chatbot stream. Closing generator."
                )
                raise
            except Exception as e:
                logger.error(f"Error in event generator: {e}", exc_info=True)
                error_event = chatbot_service.format_sse_event(
                    "chatbot.error",
                    {"error": str(e), "message": "Streaming error occurred"},
                )
                yield error_event

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chatbot streaming failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize chat stream",
        )


@router.get(
    "/sessions/{session_id}",
    status_code=status.HTTP_200_OK,
    response_model=SessionHistoryResponse,
    summary="Get conversation history for a session",
)
async def get_session_history(
    session_id: str,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    per_page: int = Query(
        default=50, ge=1, le=500, description="Number of messages per page"
    ),
    user_id: str = Depends(get_user_id),
    chatbot_service: ChatbotService = Depends(get_chatbot_service),
) -> SessionHistoryResponse:
    """
    Retrieve the conversation history for a specific session with page-based pagination.

    This endpoint returns:
    - Session metadata (creation time, last access, status)
    - Messages for the requested page in chronological order
    - Pagination metadata (current page, total pages, has_next, has_previous)

    **Authentication:**
    - Requires `User-Id` header with a valid user identifier

    Args:
        session_id: Unique session identifier
        page: Page number (1-indexed, default: 1)
        per_page: Number of messages per page (default: 50, max: 500)
        user_id: User identifier from User-Id header (required)

    Returns:
        SessionHistoryResponse with session info, message list, and pagination metadata

    Raises:
        HTTPException:
            - 400: Missing or invalid User-Id header
            - 403: User not authorized to access this session
            - 404: Session not found
            - 500: Server error retrieving history
    """
    try:
        # Verify session access, ownership, and active status
        session = await verify_session_access(
            session_id=session_id,
            user_id=user_id,
            chatbot_service=chatbot_service,
            require_active=True,
        )

        # Get messages with pagination metadata
        messages, pagination_metadata = await chatbot_service.get_session_messages(
            session_id=session_id, page=page, per_page=per_page
        )

        # Convert to response models
        session_response = SessionResponse(**session)
        message_responses = [MessageResponse(**msg) for msg in messages]

        pagination_response = PaginationMetadata(**pagination_metadata)

        return SessionHistoryResponse(
            session=session_response,
            messages=message_responses,
            pagination=pagination_response,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving session history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session history",
        )


@router.get(
    "/sessions",
    status_code=status.HTTP_200_OK,
    response_model=SessionListResponse,
    summary="List chatbot sessions",
)
async def list_sessions(
    user_id: str = Depends(get_user_id),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    per_page: int = Query(
        default=50, ge=1, le=100, description="Number of sessions per page"
    ),
    chatbot_service: ChatbotService = Depends(get_chatbot_service),
) -> SessionListResponse:
    """
    List active chatbot sessions with page-based pagination.

    This endpoint supports:
    - Filtering by user_id (from header)
    - Returns only active sessions
    - Page-based pagination with total pages info

    **Authentication:**
    - Requires `User-Id` header with a valid user identifier

    Args:
        user_id: User identifier from User-Id header (required)
        page: Page number (1-indexed, default: 1)
        per_page: Number of sessions per page (default: 50, max: 100)

    Returns:
        SessionListResponse with list of active sessions and pagination metadata

    Raises:
        HTTPException:
            - 400: Missing or invalid User-Id header
            - 500: On server error
    """
    try:
        # Get active sessions for specific user with pagination
        sessions, pagination_metadata = await chatbot_service.get_user_sessions(
            user_id=user_id,
            active_only=True,
            page=page,
            per_page=per_page,
        )

        session_responses = [SessionResponse(**session) for session in sessions]

        pagination_response = PaginationMetadata(**pagination_metadata)

        return SessionListResponse(
            sessions=session_responses,
            pagination=pagination_response,
        )

    except Exception as e:
        logger.error(f"Error listing sessions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list sessions",
        )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_200_OK,
    response_model=DeleteSessionResponse,
    summary="Delete or deactivate a session",
)
async def delete_session(
    session_id: str,
    permanent: bool = Query(
        default=False,
        description="If true, permanently delete. If false, just mark as inactive.",
    ),
    user_id: str = Depends(get_user_id),
    chatbot_service: ChatbotService = Depends(get_chatbot_service),
) -> DeleteSessionResponse:
    """
    Delete or deactivate a chatbot session.

    Two modes:
    - **Soft delete** (default): Mark session as inactive. Messages are preserved.
    - **Hard delete**: Permanently delete session and all messages (cannot be undone).

    **Authentication:**
    - Requires `User-Id` header with a valid user identifier

    Args:
        session_id: Unique session identifier
        permanent: Whether to permanently delete (default: False)
        user_id: User identifier from User-Id header (required)

    Returns:
        DeleteSessionResponse with operation result

    Raises:
        HTTPException:
            - 400: Missing or invalid User-Id header
            - 403: User not authorized to delete this session
            - 404: Session not found
            - 500: Server error during deletion
    """
    try:
        # Verify session access and ownership (allow deletion of inactive sessions)
        await verify_session_access(
            session_id=session_id,
            user_id=user_id,
            chatbot_service=chatbot_service,
            require_active=False,
        )

        if permanent:
            # Permanent deletion - delete from database
            # Note: Messages will be cascade deleted due to foreign key constraint
            deleted = await chatbot_service.delete_session_permanently(session_id)
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session {session_id} not found or already deleted.",
                )
            message = "Session and all messages permanently deleted"
        else:
            # Soft delete - mark as inactive
            success = await chatbot_service.deactivate_session(session_id)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to deactivate session",
                )
            message = "Session marked as inactive"

        return DeleteSessionResponse(
            session_id=session_id,
            success=True,
            message=message,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete session",
        )


@router.get(
    "/sessions/stats",
    status_code=status.HTTP_200_OK,
    response_model=SessionStatsResponse,
    summary="Get session and message statistics",
)
async def get_session_stats(
    chatbot_service: ChatbotService = Depends(get_chatbot_service),
) -> SessionStatsResponse:
    """
    Get statistics about all chatbot sessions and messages.

    Returns information about:
    - Total, active, and inactive sessions
    - Unique users
    - Total messages (human and AI)
    - Average messages per session

    This endpoint is useful for:
    - Monitoring chatbot usage
    - Capacity planning
    - Analytics and reporting

    Returns:
        SessionStatsResponse with comprehensive statistics

    Raises:
        HTTPException: 500 on server error
    """
    try:
        stats = await chatbot_service.get_session_stats()
        return SessionStatsResponse(**stats)
    except Exception as e:
        logger.error(f"Failed to get session stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session statistics",
        )


@router.put(
    "/sessions/{session_id}/messages/{message_id}/react",
    status_code=status.HTTP_200_OK,
    response_model=MessageReactionResponse,
    summary="Add or update a reaction to a message",
)
async def add_message_reaction(
    session_id: str,
    message_id: str,
    request: AddMessageReactionRequest,
    user_id: str = Depends(get_user_id),
    chatbot_service: ChatbotService = Depends(get_chatbot_service),
) -> MessageReactionResponse:
    """
    Add or update a like/dislike reaction to a message.

    This endpoint allows users to:
    - React to AI-generated messages with a reaction (LIKE or DISLIKE)
    - Update existing reactions
    - Provide feedback on message quality

    **Reaction Values:**
    - `LIKE`: Like (message was helpful) 👍
    - `DISLIKE`: Dislike (message was not helpful) 👎

    **Authentication:**
    - Requires `User-Id` header with a valid user identifier

    Args:
        session_id: Unique session identifier
        message_id: ID of the message to react to (UUID)
        request: AddMessageReactionRequest with reaction_type (LIKE or DISLIKE)
        user_id: User identifier from User-Id header (required)

    Returns:
        MessageReactionResponse with operation result and reaction data

    Raises:
        HTTPException:
            - 400: Missing or invalid User-Id header, invalid reaction type, or session is inactive
            - 403: User not authorized to react to messages in this session
            - 404: Session or message not found
            - 500: Server error during reaction update
    """
    try:
        # Verify session access, ownership, and active status
        await verify_session_access(
            session_id=session_id,
            user_id=user_id,
            chatbot_service=chatbot_service,
            require_active=True,
        )

        # Add reaction to message
        message = await chatbot_service.add_message_reaction(
            message_id=message_id,
            session_id=session_id,
            reaction_type=request.reaction_type.value,
        )

        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Message {message_id} not found in session {session_id} or is not an AI message",
            )

        return MessageReactionResponse(
            message_id=message["id"],
            session_id=message["session_id"],
            reaction=ReactionType(message["reaction"]) if message["reaction"] else None,
            success=True,
            message=f"Successfully added reaction {request.reaction_type.value} to message {message_id}",
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Invalid reaction type: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error adding message reaction: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add reaction to message",
        )
