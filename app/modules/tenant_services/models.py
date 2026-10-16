from datetime import datetime
from sqlalchemy import (
    DateTime,
    String,
    Boolean,
    Integer,
    ForeignKey,
    func,
    Index,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.config.database import Base

class Service(Base):
    __tablename__ = "services"
    __table_args__ = (
        Index("ix_services_tenant_name", "tenant_id", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    species: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    sizes: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    coat_types: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    price_cents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    duration_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    @property
    def size(self) -> str | None:
        if self.sizes:
            return ", ".join(self.sizes)
        return None

    @property
    def coat_type(self) -> str | None:
        if self.coat_types:
            return ", ".join(self.coat_types)
        return None