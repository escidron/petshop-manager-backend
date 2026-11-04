from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.database import Base


class DaycareModalityBillingType(str, Enum):
    HOURLY = "hourly"      # Cobrança por hora (multiplica pelas horas)
    HALF_DAY = "half_day"  # Meio período (valor fixo)
    DAILY = "daily"        # Período integral / Diária (valor fixo)


class DaycareStayType(str, Enum):
    DAILY = "daily"          # Período integral / Diária (1 dia)
    HALF_DAY = "half_day"    # Meio período (até X horas no mesmo dia)
    HOURLY = "hourly"        # Por hora (algumas horas no mesmo dia)
    MULTI_DAY = "multi_day"  # Vários dias (período com data de entrada e saída)


class DaycareStayStatus(str, Enum):
    PENDING = "pending"          # Agendado / aguardando check-in
    CHECKED_IN = "checked_in"    # No pátio (check-in realizado)
    CHECKED_OUT = "checked_out"  # Finalizado (check-out realizado)
    ABSENT = "absent"            # Faltou (direito a reposição / sem consumo)
    CANCELED = "canceled"        # Cancelado


class DaycareStayAction(str, Enum):
    CHECK_IN = "check_in"
    CHECK_OUT = "check_out"
    MARK_ABSENT = "mark_absent"
    CANCEL = "cancel"
    REOPEN = "reopen"


class DaycareTaskType(str, Enum):
    FEEDING = "feeding"        # Alimentação / Ração
    MEDICATION = "medication"  # Remédio / Cuidado


class DaycareModality(Base):
    __tablename__ = "daycare_modalities"

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

    billing_type: Mapped[str] = mapped_column(
        String(20),
        default=DaycareModalityBillingType.DAILY.value,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    max_hours: Mapped[int | None] = mapped_column(
        Integer,
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

    price_cents: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
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


class DaycarePackage(Base):
    __tablename__ = "daycare_packages"

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

    price_cents: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    is_monthly: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    frequency: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    days_quantity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    validity_days: Mapped[int | None] = mapped_column(
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

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DaycareStay(Base):
    __tablename__ = "daycare_stays"
    __table_args__ = (
        Index("ix_daycare_stays_tenant_dates", "tenant_id", "scheduled_start_at", "scheduled_end_at"),
    )

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

    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    modality_id: Mapped[int | None] = mapped_column(
        ForeignKey("daycare_modalities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    stay_type: Mapped[str] = mapped_column(
        String(20),
        default=DaycareStayType.DAILY.value,
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    unit_price_cents: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    total_price_cents: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    scheduled_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    scheduled_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    check_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    check_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=DaycareStayStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    food_info: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    belongings: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    client_package_credit_id: Mapped[int | None] = mapped_column(
        ForeignKey("client_package_credits.id", ondelete="SET NULL"),
        nullable=True,
    )

    covered_quantity: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    sale_id: Mapped[int | None] = mapped_column(
        ForeignKey("sales.id", ondelete="SET NULL"),
        nullable=True,
    )

    comanda_id: Mapped[int | None] = mapped_column(
        ForeignKey("comandas.id", ondelete="SET NULL"),
        nullable=True,
    )

    recurrence_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    recurrence_rule: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    report_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    client = relationship("Client")
    pet = relationship("Pet")
    modality = relationship("DaycareModality")
    service = relationship("Service")
    tasks: Mapped[list["DaycareTask"]] = relationship(
        "DaycareTask",
        back_populates="stay",
        cascade="all, delete-orphan",
        order_by="DaycareTask.scheduled_time.asc(), DaycareTask.id.asc()",
    )


class DaycareTask(Base):
    __tablename__ = "daycare_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    stay_id: Mapped[int] = mapped_column(
        ForeignKey("daycare_stays.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_type: Mapped[str] = mapped_column(
        String(20),
        default=DaycareTaskType.FEEDING.value,
        nullable=False,
    )

    scheduled_time: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    stay: Mapped["DaycareStay"] = relationship("DaycareStay", back_populates="tasks")


class PetHealthRecord(Base):
    __tablename__ = "pet_health_records"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(30),
        default="vaccine",
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    applied_at: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    expires_at: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    pet = relationship("Pet")
