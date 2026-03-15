from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    func,
    Table,
    Enum as SAEnum
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.config.database import Base

from sqlalchemy import (
    Column,
)

appointment_item_services = Table(
    "appointment_item_services",
    Base.metadata,
    Column(
        "appointment_item_id",
        ForeignKey("appointment_items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "service_id",
        ForeignKey("services.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

class AppointmentStatus(str, Enum):
    PENDING = "pending"            # criado, aguardando confirmação
    CONFIRMED = "confirmed"        # confirmado pelo cliente
    IN_PROGRESS = "in_progress"    # serviço em andamento
    COMPLETED = "completed"        # serviço finalizado
    CANCELED = "canceled"          # cancelado
    NO_SHOW = "no_show"             # cliente não apareceu

class AppointmentAction(str, Enum):
    CONFIRM = "confirm"
    START = "start"
    COMPLETE = "complete"
    CANCEL = "cancel"
    NO_SHOW = "no_show"
        
class Appointment(Base):
    __tablename__ = "appointments"

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
    client = relationship("Client", back_populates="appointments")

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(
            *[status.value for status in AppointmentStatus],
            name="appointment_status",
        ),
        nullable=False,
        default=AppointmentStatus.PENDING,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    items = relationship(
        "AppointmentItem",
        back_populates="appointment",
        cascade="all, delete-orphan",
    )
    
    sales = relationship(
        "app.modules.sales.models.Sale", 
        back_populates="appointment",
        lazy="select"
    )

    @property
    def is_paid(self) -> bool:
        """Checks if there's any completed sale linked to this appointment."""
        if not self.sales:
            return False
        return any(sale.status == "completed" for sale in self.sales)
    

class AppointmentItem(Base):
    __tablename__ = "appointment_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
    )

    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pets.id", ondelete="CASCADE"),
        nullable=False,
    )

    appointment = relationship("Appointment", back_populates="items")
    pet = relationship("Pet")

    services = relationship(
        "Service",
        secondary="appointment_item_services",
    )