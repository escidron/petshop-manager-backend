from datetime import datetime, date
from sqlalchemy import (
    DateTime,
    String,
    Boolean,
    ForeignKey,
    Integer,
    func,
    Date,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.database import Base


class Pet(Base):
    __tablename__ = "pets"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 🔐 Multi-tenant
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

    # 📌 Obrigatórios
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    species: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # dog, cat, etc

    # 🧬 Básicos (opcionais)
    breed: Mapped[str | None] = mapped_column(String(100))
    
    gender: Mapped[str | None] = mapped_column(
        String(10),
        default="unknown",  # male | female | unknown
        index=True,
    )

    is_neutered: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        default=None,
    )

    # 📏 Porte
    size: Mapped[str | None] = mapped_column(
        String(5)
    )  # PP | P | M | G | GG

    # 🐕 Pelagem
    coat_type: Mapped[str | None] = mapped_column(
        String(30)
    )  # short | long | double | curly | hairless | etc

    coat_color: Mapped[str | None] = mapped_column(
        String(50)
    )  # preto, branco, marrom, caramelo...

    # 🎂 Idade (quando não souber data exata)
    age: Mapped[int | None] = mapped_column(Integer)
    age_unit: Mapped[str | None] = mapped_column(
        String(10)
    )  # months | years

    # 📅 Data de nascimento (opcional)
    birth_date: Mapped[date | None] = mapped_column(Date)

    # 📝 Observações gerais
    notes: Mapped[str | None] = mapped_column(Text)

    # 🔄 Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    is_deceased: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # ⏱ Auditoria
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # 🔗 Relacionamentos
    client = relationship("Client", back_populates="pets")
    photos = relationship("PetPhoto", back_populates="pet", cascade="all, delete-orphan")
    client_packages = relationship("ClientPackage", secondary="client_package_pets", back_populates="pets")

    # 🧠 Helpers
    @property
    def owner_name(self) -> str | None:
        return self.client.name if self.client else None


class PetPhoto(Base):
    __tablename__ = "pet_photos"

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
    photo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_profile: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # 🔗 Relacionamentos
    pet = relationship("Pet", back_populates="photos")

