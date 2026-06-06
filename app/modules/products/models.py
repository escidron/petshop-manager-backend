from sqlalchemy import String, Boolean, ForeignKey, Numeric, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.config.database import Base


class Product(Base):
    __tablename__ = "products"

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

    unit: Mapped[str | None] = mapped_column(
        String(10), default="UN", nullable=True
    )
