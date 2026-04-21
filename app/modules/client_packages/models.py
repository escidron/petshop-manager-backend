from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.config.database import Base


class ClientPackage(Base):
    """Instância de um pacote vendido para um pet específico."""

    __tablename__ = "client_packages"

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
    # Referência ao template do pacote (pode ser nulo se o pacote for deletado)
    package_id: Mapped[int | None] = mapped_column(
        ForeignKey("packages.id", ondelete="SET NULL"),
        nullable=True,
    )
    package_name: Mapped[str] = mapped_column(String(150), nullable=False)  # snapshot
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    credits: Mapped[list["ClientPackageCredit"]] = relationship(
        "ClientPackageCredit",
        back_populates="client_package",
        cascade="all, delete-orphan",
    )
    package = relationship("Package")
    pet = relationship("Pet")
    client = relationship("Client")


class ClientPackageCredit(Base):
    """Créditos de um serviço dentro de um pacote comprado."""

    __tablename__ = "client_package_credits"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_package_id: Mapped[int] = mapped_column(
        ForeignKey("client_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"),
        nullable=True,
    )
    service_name: Mapped[str] = mapped_column(String(150), nullable=False)  # snapshot
    total_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    used_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    client_package: Mapped["ClientPackage"] = relationship(
        "ClientPackage", back_populates="credits"
    )
    service = relationship("Service")

    @property
    def remaining_qty(self) -> int:
        return self.total_qty - self.used_qty
