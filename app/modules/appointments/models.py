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

appointment_services = Table(
    "appointment_services",
    Base.metadata,
    Column(
        "appointment_id",
        ForeignKey("appointments.id", ondelete="CASCADE"),
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
        ForeignKey("clients.id"),
        nullable=False,
    )

    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pets.id"),
        nullable=False,
    )

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    client = relationship("Client", lazy="joined")
    pet = relationship("Pet", lazy="joined")

    services = relationship(
        "Service",
        secondary=appointment_services,
        lazy="joined",
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
