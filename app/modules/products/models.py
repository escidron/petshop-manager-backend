from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, Numeric, Integer, Index, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.database import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_tenant_name", "tenant_id", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150), nullable=False
    )

    sku: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )

    description: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    category: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    price: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    cost: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    quantity: Mapped[int] = mapped_column(
        Integer, default=0
    )

    barcode: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    
    ncm: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    
    cest: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    
    cfop: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    
    csosn: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    
    cst_pis: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    
    cst_cofins: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )

    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )

    min_stock: Mapped[int] = mapped_column(
        Integer, default=0
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True
    )

    is_internal_use: Mapped[bool] = mapped_column(
        Boolean, default=False
    )

    unit: Mapped[str | None] = mapped_column(
        String(10), default="UN", nullable=True
    )

    photos = relationship(
        "ProductPhoto",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductPhoto.id",
    )


class ProductPhoto(Base):
    __tablename__ = "product_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    photo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    product = relationship("Product", back_populates="photos")
