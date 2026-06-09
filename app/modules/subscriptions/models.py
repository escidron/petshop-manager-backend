from datetime import datetime
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.database import Base


class TenantCard(Base):
    """Mapeia card_ids do Pagar.me para tenants.
    
    Necessário porque no Sandbox o mesmo CPF gera o mesmo pagarme_customer_id,
    então não podemos filtrar cartões só pelo customer.
    Em produção também garante isolamento caso um owner tenha vários tenants.
    
    Não armazena dados sensíveis do cartão — apenas o ID do Pagar.me.
    Os metadados (brand, last4, etc.) são sempre buscados do Pagar.me.
    """
    __tablename__ = "tenant_cards"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    pagarme_card_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )

    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    tenant = relationship("Tenant")



class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
    )

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(String(30), nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    canceled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    pagarme_subscription_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True
    )

    payment_method: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="card",
        default="card",
    )

    tenant = relationship("Tenant")
    plan = relationship("Plan")
    charges = relationship("SubscriptionCharge", back_populates="subscription", cascade="all, delete-orphan")


class SubscriptionCharge(Base):
    __tablename__ = "subscription_charges"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
    )

    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id"),
        nullable=False,
    )

    pagarme_charge_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )

    amount: Mapped[int] = mapped_column(nullable=False)

    status: Mapped[str] = mapped_column(String(50), nullable=False)

    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)

    pix_qr_code: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    pix_qr_code_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    subscription = relationship("Subscription", back_populates="charges")