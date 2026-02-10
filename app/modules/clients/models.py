from datetime import date
from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.config.database import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # -------- Dados básicos --------
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    document_type: Mapped[str | None] = mapped_column(String(10))
    document: Mapped[str | None] = mapped_column(String(20))
    birth_date: Mapped[date | None] = mapped_column(String(10))
    # -------- Telefones --------
    phone: Mapped[str | None] = mapped_column(String(20), nullable=False)

    phone_secondary_name: Mapped[str | None] = mapped_column(String(50))
    phone_secondary: Mapped[str | None] = mapped_column(String(20))

    phone_tertiary_name: Mapped[str | None] = mapped_column(String(50))
    phone_tertiary: Mapped[str | None] = mapped_column(String(20))

    # -------- Endereço --------
    cep: Mapped[str | None] = mapped_column(String(10))
    street: Mapped[str | None] = mapped_column(String(150))
    number: Mapped[str | None] = mapped_column(String(20))
    complement: Mapped[str | None] = mapped_column(String(100))
    neighborhood: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))

    # -------- Redes sociais --------
    instagram: Mapped[str | None] = mapped_column(String(255))
    facebook: Mapped[str | None] = mapped_column(String(255))
    x: Mapped[str | None] = mapped_column(String(255))
