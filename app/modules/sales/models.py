from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    String,
    ForeignKey,
    Numeric,
    DateTime,
    func,
    Integer,
    Enum,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.database import Base


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 🔐 Multi-tenant
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    pet_id: Mapped[int | None] = mapped_column(
        ForeignKey("pets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    comanda_id: Mapped[int | None] = mapped_column(
        ForeignKey("comandas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    cash_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("cash_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    total_amount: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    discount_amount: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0.0, nullable=False
    )

    payment_method: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # pix, credit_card, debit_card, money, other, package

    status: Mapped[str] = mapped_column(
        String(20), default="completed", nullable=False
    )  # completed, canceled

    # ⏱ Auditoria
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relacionamentos
    items = relationship(
        "SaleItem", back_populates="sale", cascade="all, delete-orphan"
    )
    client = relationship("Client")
    pet = relationship("Pet")
    appointment = relationship("Appointment", back_populates="sales")
    cash_session = relationship("CashSession", back_populates="sales")
    comanda = relationship("Comanda", back_populates="sales")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    sale_id: Mapped[int] = mapped_column(
        ForeignKey("sales.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "product" ou "service" ou "package"

    item_id: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    name: Mapped[str] = mapped_column(
        String(150), nullable=False
    )  # Snapshot of the name at the time of sale

    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )

    unit_price: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    subtotal: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )

    sale = relationship("Sale", back_populates="items")


class Comanda(Base):
    __tablename__ = "comandas"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20), default="open", nullable=False, index=True
    )  # "open", "completed", "canceled"

    total_amount: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0.0, nullable=False
    )

    discount_amount: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0.0, nullable=False
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relacionamentos
    items = relationship(
        "ComandaItem", back_populates="comanda", cascade="all, delete-orphan", lazy="joined"
    )
    client = relationship("Client", lazy="joined")
    appointment = relationship("Appointment", lazy="joined")
    sales = relationship("Sale", back_populates="comanda")


class ComandaItem(Base):
    __tablename__ = "comanda_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    comanda_id: Mapped[int] = mapped_column(
        ForeignKey("comandas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "product", "service", "package"

    item_id: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    name: Mapped[str] = mapped_column(
        String(150), nullable=False
    )

    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )

    unit_price: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=0.0
    )

    subtotal: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=0.0
    )

    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )

    pet_ids: Mapped[list[int] | None] = mapped_column(
        JSON, nullable=True
    )

    client_package_id_to_pay: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    unit: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default="UN"
    )

    comanda = relationship("Comanda", back_populates="items")
