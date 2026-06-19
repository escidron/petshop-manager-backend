from datetime import datetime
from sqlalchemy import (
    DateTime,
    String,
    Boolean,
    Integer,
    ForeignKey,
    func,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.config.database import Base
from app.enums import PetSize, PetSpecies

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

    species: Mapped[PetSpecies | None] = mapped_column(
        nullable=True,
    )

    size: Mapped[PetSize | None] = mapped_column(
        nullable=True,
    )

    coat_type: Mapped[str | None] = mapped_column(
        String(50),
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