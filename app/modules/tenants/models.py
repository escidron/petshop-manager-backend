from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    type_id: Mapped[int] = mapped_column(
        ForeignKey("tenant_types.id"),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    type = relationship("TenantType")
