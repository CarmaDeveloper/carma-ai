"""Repository for SessionModel database operations with Protocol."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple, Protocol
from uuid import UUID
from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import SessionModel
from app.models.message import MessageModel
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class SessionRepositoryProtocol(Protocol):
    """Protocol for SessionRepository interface."""

    async def create(
        self,
        session_id: UUID,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionModel: ...

    async def get_by_id(self, session_id: UUID) -> Optional[SessionModel]: ...

    async def get_user_sessions(
        self,
        user_id: str,
        active_only: bool = True,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[SessionModel], Dict[str, Any]]: ...

    async def get_user_sessions_count(
        self, user_id: str, active_only: bool = True
    ) -> int: ...

    async def update_access_time(self, session_id: UUID) -> None: ...

    async def deactivate(self, session_model: SessionModel) -> bool: ...

    async def delete_permanently(self, session_model: SessionModel) -> bool: ...

    async def delete_old_sessions(self, retention_days: int) -> int: ...

    async def get_stats(self) -> Dict[str, Any]: ...


class SessionRepository:
    """Repository for SessionModel operations with injected session."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session."""
        self.session = session

    async def create(
        self,
        session_id: UUID,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionModel:
        """Create a new session."""
        new_session = SessionModel(
            session_id=session_id,
            user_id=user_id,
            title=title,
            session_metadata=metadata or {},
        )
        self.session.add(new_session)
        await self.session.commit()
        await self.session.refresh(new_session)
        logger.info(f"Created new session: {session_id}")
        return new_session

    async def get_by_id(self, session_id: UUID) -> Optional[SessionModel]:
        """Get session by ID."""
        result = await self.session.execute(
            select(SessionModel).where(SessionModel.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_user_sessions(
        self,
        user_id: str,
        active_only: bool = True,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[SessionModel], Dict[str, Any]]:
        """Get all sessions for a user with pagination."""
        query = select(SessionModel).where(SessionModel.user_id == user_id)

        if active_only:
            query = query.where(SessionModel.is_active == True)

        query = query.order_by(SessionModel.last_accessed_at.desc())

        # Get total count
        count_query = (
            select(func.count())
            .select_from(SessionModel)
            .where(SessionModel.user_id == user_id)
        )
        if active_only:
            count_query = count_query.where(SessionModel.is_active == True)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * per_page
        query = query.limit(per_page).offset(offset)

        result = await self.session.execute(query)
        sessions = result.scalars().all()

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

        return list(sessions), pagination_metadata

    async def get_user_sessions_count(
        self, user_id: str, active_only: bool = True
    ) -> int:
        """Get total count of sessions for a user."""
        query = (
            select(func.count())
            .select_from(SessionModel)
            .where(SessionModel.user_id == user_id)
        )
        if active_only:
            query = query.where(SessionModel.is_active == True)

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def update_access_time(self, session_id: UUID) -> None:
        """Update the last accessed timestamp."""
        stmt = (
            update(SessionModel)
            .where(
                SessionModel.session_id == session_id, SessionModel.is_active == True
            )
            .values(last_accessed_at=datetime.now(timezone.utc))
        )
        result = await self.session.execute(stmt)
        await self.session.commit()

        if result.rowcount == 0:
            logger.warning(
                f"Failed to update session access time for session {session_id}: not found or inactive."
            )
        else:
            logger.debug(f"Updated session access time: {session_id}")

    async def deactivate(self, session_model: SessionModel) -> bool:
        """Mark session as inactive."""
        session_model.is_active = False
        session_model.last_accessed_at = datetime.now(timezone.utc)
        await self.session.commit()
        logger.info(f"Deactivated session: {session_model.session_id}")
        return True

    async def delete_permanently(self, session_model: SessionModel) -> bool:
        """Permanently delete session and its messages."""
        await self.session.delete(session_model)
        await self.session.commit()
        logger.info(f"Permanently deleted session: {session_model.session_id}")
        return True

    async def delete_old_sessions(self, retention_days: int) -> int:
        """Delete old inactive sessions."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=retention_days)

        result = await self.session.execute(
            delete(SessionModel).where(
                SessionModel.is_active == False,
                SessionModel.last_accessed_at < cutoff_time,
            )
        )
        await self.session.commit()

        count = result.rowcount
        if count > 0:
            logger.info(
                f"Deleted {count} old sessions (retention: {retention_days} days)"
            )

        return count

    async def get_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        # Session stats
        session_stats_query = select(
            func.count().label("total_sessions"),
            func.count()
            .filter(SessionModel.is_active == True)
            .label("active_sessions"),
            func.count()
            .filter(SessionModel.is_active == False)
            .label("inactive_sessions"),
            func.count(func.distinct(SessionModel.user_id))
            .filter(SessionModel.user_id.isnot(None))
            .label("unique_users"),
        ).select_from(SessionModel)

        result = await self.session.execute(session_stats_query)
        stats_row = result.first()

        # Message stats
        message_stats_query = select(
            func.count().label("total_messages"),
            func.count()
            .filter(MessageModel.message_type == "human")
            .label("human_messages"),
            func.count().filter(MessageModel.message_type == "ai").label("ai_messages"),
        ).select_from(MessageModel)

        result = await self.session.execute(message_stats_query)
        message_row = result.first()

        # Average messages per session - using subquery
        subquery = (
            select(
                MessageModel.session_id,
                func.count(MessageModel.id).label("msg_count"),
            )
            .group_by(MessageModel.session_id)
            .subquery()
        )

        avg_result = await self.session.execute(select(func.avg(subquery.c.msg_count)))
        avg_messages = avg_result.scalar()

        return {
            "sessions": {
                "total": stats_row.total_sessions or 0,
                "active": stats_row.active_sessions or 0,
                "inactive": stats_row.inactive_sessions or 0,
                "unique_users": stats_row.unique_users or 0,
            },
            "messages": {
                "total": message_row.total_messages or 0,
                "human": message_row.human_messages or 0,
                "ai": message_row.ai_messages or 0,
                "avg_per_session": round(avg_messages, 2) if avg_messages else 0,
            },
        }
