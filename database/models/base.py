"""
Base Database Models and Declarative Mixins.
Implements UUID primary keys, UTC timestamp auditing, and soft delete capabilities.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base, declared_attr


class CustomBase:
    """Base mixin providing common fields across all CCTV entities."""

    @declared_attr
    def __tablename__(cls) -> str:
        # Default table name: lowercase class name
        return cls.__name__.lower()

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)


Base = declarative_base(cls=CustomBase)
