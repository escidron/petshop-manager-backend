from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    String, Boolean, ForeignKey, DateTime, Date,
    Numeric, func, Enum as SAEnum, Table, Column,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.database import Base


commission_rule_services = Table(
    "commission_rule_services",
    Base.metadata,
    Column("rule_id", ForeignKey("commission_rules.id", ondelete="CASCADE"), primary_key=True),
    Column("service_id", ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
)


class CommissionRule(Base):
    __tablename__ = "commission_rules"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    applies_to: Mapped[str] = mapped_column(
        SAEnum("service", "product", "both", name="commission_applies_to"),
        nullable=False,
        default="service",
    )

    commission_type: Mapped[str] = mapped_column(
        SAEnum("percentage", "fixed", name="commission_type"),
        nullable=False,
    )

    value: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)

    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    employee = relationship("Employee", foreign_keys=[employee_id])
    services = relationship("Service", secondary="commission_rule_services")

    @property
    def service_ids(self) -> list[int]:
        return [s.id for s in self.services]


class CommissionEntry(Base):
    __tablename__ = "commission_entries"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sale_id: Mapped[int] = mapped_column(
        ForeignKey("sales.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sale_item_id: Mapped[int] = mapped_column(
        ForeignKey("sale_items.id", ondelete="CASCADE"),
        nullable=False,
    )

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("commission_rules.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Snapshot — imutável após criação
    commission_type: Mapped[str] = mapped_column(String(20), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    commission_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    status: Mapped[str] = mapped_column(
        SAEnum("pending", "paid", name="commission_entry_status"),
        nullable=False,
        default="pending",
    )

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    employee = relationship("Employee", foreign_keys=[employee_id])
    rule = relationship("CommissionRule", foreign_keys=[rule_id])
