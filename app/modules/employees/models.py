from datetime import datetime
from enum import Enum
from sqlalchemy import String, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SAEnum

from app.config.database import Base


class EmployeeRole(str, Enum):
    GROOMER = "groomer"
    VET = "vet"
    SALESPERSON = "salesperson"
    OTHER = "other"


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    role: Mapped[EmployeeRole] = mapped_column(
        SAEnum(*[r.value for r in EmployeeRole], name="employee_role"),
        nullable=False,
        default=EmployeeRole.OTHER,
    )

    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
