from datetime import datetime
from sqlalchemy import DateTime, String, Boolean, ForeignKey, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional

from app.config.database import Base


class TenantType(Base):
    __tablename__ = "tenant_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    document: Mapped[str | None] = mapped_column(String(20), nullable=True)

    type_id: Mapped[int] = mapped_column(
        ForeignKey("tenant_types.id"),
        nullable=False,
    )
    onboarding_step: Mapped[str] = mapped_column(
        String(50),
        default="services",
        nullable=False,
    )
    pagarme_customer_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True
    )

    working_hours: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    type = relationship("TenantType")
