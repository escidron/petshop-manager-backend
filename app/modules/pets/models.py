from datetime import datetime
from sqlalchemy import DateTime, String, Boolean, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.database import Base


class Pet(Base):
    __tablename__ = "pets"

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

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    species: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # dog, cat, etc

    breed: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    age: Mapped[int | None] = mapped_column(Integer, nullable=True)

    gender: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="unknown",  # male | female | unknown
        index=True,
    )

    ageUnit: Mapped[str] = mapped_column(
        String(10),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    client = relationship("Client", backref="pets")
    
    @property
    def owner_name(self) -> str | None:
        return self.client.name if self.client else None