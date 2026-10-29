from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.database import Base

class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    appointment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True
    )
    phone_number: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # "inbound" ou "outbound"
    content: Mapped[str] = mapped_column(String(1000), nullable=False)
    buttons: Mapped[Optional[List[dict]]] = mapped_column(JSON, nullable=True)  # ex: [{"id": "confirm", "text": "Confirmar"}]
    status: Mapped[str] = mapped_column(String(20), default="sent", server_default="sent", index=True)  # queued, sending, sent, failed, delivered, read
    trigger_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    meta_message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0, server_default="0")
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    refunded: Mapped[bool] = mapped_column(default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    tenant = relationship("Tenant")
    appointment = relationship("Appointment")

class WhatsAppTemplate(Base):
    __tablename__ = "whatsapp_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # ex: "reminder_24h", "instant_confirmation", "pet_ready", "appointment_canceled", "fallback_invalid"
    message_template: Mapped[str] = mapped_column(String(1000), nullable=False)
    buttons: Mapped[Optional[List[dict]]] = mapped_column(JSON, nullable=True)  # ex: [{"id": "confirm", "text": "Confirmar"}]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    tenant = relationship("Tenant")
