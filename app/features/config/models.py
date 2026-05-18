"""ORM model for the runtime configuration override store.

The ``app_config`` table is a small key/value store. Each row overrides one
``Settings`` field; the value is wrapped as ``{"v": <scalar>}`` so the JSONB
column holds a consistent object shape regardless of the scalar type.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppConfig(Base):
    """Key/value override store for runtime-editable settings.

    Attributes:
        key: The ``Settings`` field name being overridden (primary key).
        value: JSONB envelope ``{"v": <scalar>}`` carrying the override value.
        updated_at: Timestamp of the last write.
    """

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
