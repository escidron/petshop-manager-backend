from datetime import datetime
from enum import Enum
from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Enum as SAEnum,
    func,
    Table,
    Column
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)
from app.config.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.tenant_services.models import Service
    from app.modules.pets.models import Pet
    from app.modules.clients.models import Client

class WaitingListStatus(str, Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    CANCELED = "canceled"

class WaitingListPeriod(str, Enum):
    ANY = "any"
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"

# Tabela associativa para serviços na lista de espera
waiting_list_services = Table(
    "waiting_list_services",
    Base.metadata,
    Column("waiting_list_item_id", ForeignKey("waiting_list_items.id", ondelete="CASCADE"), primary_key=True),
    Column("service_id", ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
)

class WaitingListEntry(Base):
    __tablename__ = "waiting_list_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    client = relationship("Client")

    preferred_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    preferred_period: Mapped[WaitingListPeriod] = mapped_column(
        SAEnum(WaitingListPeriod, name="waiting_list_period"),
        nullable=False,
        default=WaitingListPeriod.ANY,
    )

    status: Mapped[WaitingListStatus] = mapped_column(
        SAEnum(WaitingListStatus, name="waiting_list_status"),
        nullable=False,
        default=WaitingListStatus.PENDING,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    items: Mapped[list["WaitingListItem"]] = relationship(
        "WaitingListItem",
        back_populates="waiting_list_entry",
        cascade="all, delete-orphan",
    )

class WaitingListItem(Base):
    __tablename__ = "waiting_list_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    waiting_list_entry_id: Mapped[int] = mapped_column(
        ForeignKey("waiting_list_entries.id", ondelete="CASCADE"),
        nullable=False,
    )

    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pets.id", ondelete="CASCADE"),
        nullable=False,
    )
    pet = relationship("Pet")

    waiting_list_entry = relationship("WaitingListEntry", back_populates="items")

    services: Mapped[list["Service"]] = relationship(
        "Service",
        secondary=waiting_list_services,
    )
