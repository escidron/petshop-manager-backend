from datetime import datetime
from sqlalchemy import (
    DateTime,
    String,
    Boolean,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.config.database import Base

class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    price_cents: Mapped[int] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="BRL")

    billing_cycle: Mapped[str] = mapped_column(String(20))

    trial_days: Mapped[int] = mapped_column(default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )