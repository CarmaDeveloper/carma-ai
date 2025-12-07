"""Repository for MessageModel database operations with Protocol."""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple, Protocol
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import MessageModel
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class MessageRepositoryProtocol(Protocol):
    """Protocol for MessageRepository interface."""

    async def create(
        self,
        message_id: UUID,
        session_id: UUID,
        message_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
    ) -> MessageModel: ...

    async def get_by_session(
        self,
        session_id: UUID,
        page: int = 1,
        per_page: int = 50,
        order: str = "DESC",
    ) -> Tuple[List[MessageModel], Dict[str, Any]]: ...

    async def get_count_by_session(self, session_id: UUID) -> int: ...

    async def get_by_id(
        self, message_id: UUID, session_id: UUID
    ) -> Optional[MessageModel]: ...

    async def add_reaction(
        self, message_model: MessageModel, reaction_type: str
    ) -> Optional[MessageModel]: ...


class MessageRepository:
    """Repository for MessageModel operations with injected session."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session."""
        self.session = session

    async def create(
        self,
        message_id: UUID,
        session_id: UUID,
        message_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
    ) -> MessageModel:
        """Create a new message."""
        if message_type not in ("human", "ai"):
            raise ValueError(
                f"Invalid message_type: {message_type}. Must be 'human' or 'ai'"
            )

        new_message = MessageModel(
            id=message_id,
            session_id=session_id,
            message_type=message_type,
            content=content,
            message_metadata=metadata or {},
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )
        self.session.add(new_message)
        await self.session.commit()
        await self.session.refresh(new_message)
        logger.debug(
            f"Added {message_type} message to session {session_id} (id: {message_id})"
        )
        return new_message

    async def get_by_session(
        self,
        session_id: UUID,
        page: int = 1,
        per_page: int = 50,
        order: str = "DESC",
    ) -> Tuple[List[MessageModel], Dict[str, Any]]:
        """Get all messages for a session with pagination."""
        if order.upper() not in ("ASC", "DESC"):
            raise ValueError(
                f"Invalid order parameter: {order}. Must be 'ASC' or 'DESC'"
            )

        query = select(MessageModel).where(MessageModel.session_id == session_id)

        # Order by created_at
        if order.upper() == "ASC":
            query = query.order_by(MessageModel.created_at.asc())
        else:
            query = query.order_by(MessageModel.created_at.desc())

        # Get total count
        count_query = (
            select(func.count())
            .select_from(MessageModel)
            .where(MessageModel.session_id == session_id)
        )
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * per_page
        query = query.limit(per_page).offset(offset)

        result = await self.session.execute(query)
        messages = result.scalars().all()

        # Calculate pagination metadata
        total_pages = (total + per_page - 1) // per_page
        pagination_metadata = {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }

        logger.debug(f"Retrieved {len(messages)} messages for session {session_id}")
        return list(messages), pagination_metadata

    async def get_count_by_session(self, session_id: UUID) -> int:
        """Get total number of messages for a session."""
        query = (
            select(func.count())
            .select_from(MessageModel)
            .where(MessageModel.session_id == session_id)
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_by_id(
        self, message_id: UUID, session_id: UUID
    ) -> Optional[MessageModel]:
        """Get message by ID and session ID (only AI messages for reactions)."""
        result = await self.session.execute(
            select(MessageModel).where(
                MessageModel.id == message_id,
                MessageModel.session_id == session_id,
                MessageModel.message_type
                == "ai",  # Only AI messages can have reactions
            )
        )
        return result.scalar_one_or_none()

    async def add_reaction(
        self, message_model: MessageModel, reaction_type: str
    ) -> Optional[MessageModel]:
        """Add or update reaction on a message."""
        if reaction_type not in ("LIKE", "DISLIKE"):
            raise ValueError(
                f"Invalid reaction_type: {reaction_type}. Must be 'LIKE' or 'DISLIKE'"
            )

        if message_model.message_type != "ai":
            logger.warning(f"Cannot add reaction to non-AI message: {message_model.id}")
            return None

        # Update metadata with reaction_updated_at
        if not isinstance(message_model.message_metadata, dict):
            message_model.message_metadata = {}
        message_model.message_metadata["reaction_updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        message_model.reaction = reaction_type
        await self.session.commit()
        await self.session.refresh(message_model)

        logger.debug(f"Added reaction {reaction_type} to message {message_model.id}")
        return message_model
