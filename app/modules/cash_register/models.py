from datetime import datetime
from sqlalchemy import (
    String,
    ForeignKey,
    Numeric,
    DateTime,
    Text,
    Boolean,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.database import Base


class CashRegister(Base):
    __tablename__ = "cash_registers"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Multi-tenant
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100), default="Caixa Principal", nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relacionamentos
    tenant = relationship("Tenant")
    sessions = relationship("CashSession", back_populates="cash_register", cascade="all, delete-orphan")


class CashSession(Base):
    __tablename__ = "cash_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    cash_register_id: Mapped[int] = mapped_column(
        ForeignKey("cash_registers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20), default="open", nullable=False, index=True
    )  # "open", "closed"

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    opened_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    initial_amount: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0.0, nullable=False
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    closed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    expected_closing_amount: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    actual_closing_amount: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    difference_amount: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    closing_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relacionamentos
    tenant = relationship("Tenant")
    cash_register = relationship("CashRegister", back_populates="sessions")
    opened_by = relationship("User", foreign_keys=[opened_by_user_id])
    closed_by = relationship("User", foreign_keys=[closed_by_user_id])
    movements = relationship(
        "CashMovement", back_populates="session", cascade="all, delete-orphan", order_by="CashMovement.created_at.desc()"
    )
    sales = relationship("Sale", back_populates="cash_session")


class CashMovement(Base):
    __tablename__ = "cash_movements"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    session_id: Mapped[int] = mapped_column(
        ForeignKey("cash_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )  # "opening", "sale", "sale_cancel", "supply", "bleed", "closing"

    amount: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    balance_after: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    sale_id: Mapped[int | None] = mapped_column(
        ForeignKey("sales.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    destination_or_origin: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )

    description: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relacionamentos
    tenant = relationship("Tenant")
    session = relationship("CashSession", back_populates="movements")
    user = relationship("User")
    sale = relationship("Sale")


class CashDestinationAccount(Base):
    __tablename__ = "cash_destination_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Multi-tenant
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # Ex: "Caixa Administrativo", "Cofre", "Conta Itaú"

    account_type: Mapped[str] = mapped_column(
        String(50), default="internal_cash", nullable=False
    )  # "internal_cash", "bank_account", "safe", "other"

    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relacionamentos
    tenant = relationship("Tenant")

