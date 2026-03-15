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

    total_amount: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    payment_method: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # pix, credit, debit, money

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
    appointment = relationship("Appointment")


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
    )  # "product" ou "service"

    item_id: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    name: Mapped[str] = mapped_column(
        String(150), nullable=False
    ) # Snapshot of the name at the time of sale

    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )

    unit_price: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    subtotal: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    sale = relationship("Sale", back_populates="items")
