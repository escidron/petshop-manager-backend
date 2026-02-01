from datetime import datetime
from sqlalchemy import (
    DateTime,
    String,
    Boolean,
    Integer,
    ForeignKey,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.config.database import Base


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    description: Mapped[str | None] = mapped_column(
        String(255)
    )

    duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    price_cents: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
