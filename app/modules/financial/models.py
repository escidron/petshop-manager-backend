from datetime import datetime
from sqlalchemy import (
    String,
    Boolean,
    ForeignKey,
    Numeric,
    Integer,
    DateTime,
    func,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.database import Base


class DREAccount(Base):
    __tablename__ = "dre_accounts"
    __table_args__ = (
        Index("ix_dre_accounts_tenant_group", "tenant_id", "group_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150), nullable=False
    )

    code: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    group_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # gross_revenue, cmv, fixed_expense, variable_expense, financial_result

    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    system_source: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # sales_products, sales_services, cmv_products, commissions

    order_index: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant = relationship("Tenant")
    entries = relationship(
        "DREEntry", back_populates="account", cascade="all, delete-orphan"
    )


class DREEntry(Base):
    __tablename__ = "dre_entries"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "account_id",
            "competence_year",
            "competence_month",
            name="uq_dre_entry_tenant_account_period",
        ),
        Index(
            "ix_dre_entries_tenant_period",
            "tenant_id",
            "competence_year",
            "competence_month",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("dre_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    competence_year: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )

    competence_month: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True  # 1 to 12
    )

    amount: Mapped[float] = mapped_column(
        Numeric(12, 2), default=0.0, nullable=False
    )

    notes: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant = relationship("Tenant")
    account = relationship("DREAccount", back_populates="entries")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
