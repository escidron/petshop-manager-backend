from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.packages.models import Package, PackageItem
from app.modules.pets.models import Pet
from .repository import ClientPackageRepository
from .schemas import ClientPackageSellRequest, ClientPackageResponse
from .models import ClientPackage, ClientPackageCredit, ClientPackageUsage


class ClientPackageService:
    def __init__(self):
        self.repo = ClientPackageRepository()

    def sell(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        data: ClientPackageSellRequest,
        is_paid: bool = False,
    ) -> ClientPackageResponse:
        # Valida pets
        pets = (
            db.query(Pet)
            .filter(
                Pet.id.in_(data.pet_ids),
                Pet.client_id == client_id,
                Pet.tenant_id == tenant_id,
            )
            .all()
        )
        if not pets or len(pets) != len(data.pet_ids):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Um ou mais pets não encontrados")

        # Valida pacote
        package = (
            db.query(Package)
            .filter(
                Package.id == data.package_id,
                Package.tenant_id == tenant_id,
                Package.is_active == True,
            )
            .first()
        )
        if not package:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacote não encontrado")

        # Monta créditos a partir dos itens do pacote (apenas serviços)
        service_items = [
            item for item in package.items if item.service_id is not None
        ]
        if not service_items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pacote não possui serviços",
            )

        credits_data = [
            {
                "service_id": item.service_id,
                "service_name": item.service.name if item.service else "Serviço removido",
                "total_qty": item.quantity,
            }
            for item in service_items
        ]

        expires_at = None
        if package.validity_days:
            from datetime import UTC, datetime, timedelta
            expires_at = datetime.now(UTC) + timedelta(days=package.validity_days)

        return self.repo.create(
            db=db,
            tenant_id=tenant_id,
            client_id=client_id,
            pet_ids=data.pet_ids,
            package_id=package.id,
            package_name=package.name,
            credits_data=credits_data,
            expires_at=expires_at,
            is_paid=is_paid,
        )

    def list_by_pet(
        self, db: Session, tenant_id: int, pet_id: int
    ) -> list[ClientPackageResponse]:
        return self.repo.list_by_pet(db, tenant_id, pet_id)

    def list_unpaid_packages(
        self,
        db: Session,
        tenant_id: int,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ):
        items, total = self.repo.list_unpaid(db, tenant_id, limit, offset, search)
        return {"items": items, "total": total}

    def list_by_client(
        self, db: Session, tenant_id: int, client_id: int
    ) -> list[ClientPackageResponse]:
        return self.repo.list_by_client(db, tenant_id, client_id)

    def deactivate(
        self, db: Session, tenant_id: int, client_package_id: int
    ) -> None:
        cp = self.repo.get_by_id_scoped(db, tenant_id, client_package_id)
        if not cp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pacote não encontrado")
        self.repo.deactivate(db, cp)

    def consume_credit(
        self,
        db: Session,
        tenant_id: int,
        credit_id: int,
        user_id: int | None = None,
        notes: str | None = None,
        consumed_at: datetime | None = None,
    ) -> ClientPackageCredit:
        credit = (
            db.query(ClientPackageCredit)
            .join(ClientPackage)
            .filter(
                ClientPackageCredit.id == credit_id,
                ClientPackage.tenant_id == tenant_id,
            )
            .first()
        )
        if not credit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Crédito do pacote não encontrado",
            )

        if credit.used_qty >= credit.total_qty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Todos os créditos para este serviço já foram consumidos",
            )

        credit.used_qty += 1
        db.add(credit)

        usage_kwargs = {
            "tenant_id": tenant_id,
            "client_package_id": credit.client_package_id,
            "credit_id": credit.id,
            "change_qty": 1,
            "notes": notes or "Consumo manual",
            "user_id": user_id,
        }
        if consumed_at is not None:
            usage_kwargs["created_at"] = consumed_at

        usage = ClientPackageUsage(**usage_kwargs)
        db.add(usage)

        client_pkg = credit.client_package
        db.refresh(client_pkg, ["credits"])
        if all(c.used_qty >= c.total_qty for c in client_pkg.credits):
            client_pkg.is_active = False
            db.add(client_pkg)

        db.commit()
        db.refresh(credit)
        return credit

    def revert_credit(
        self, db: Session, tenant_id: int, credit_id: int, user_id: int | None = None, notes: str = None
    ) -> ClientPackageCredit:
        credit = (
            db.query(ClientPackageCredit)
            .join(ClientPackage)
            .filter(
                ClientPackageCredit.id == credit_id,
                ClientPackage.tenant_id == tenant_id,
            )
            .first()
        )
        if not credit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Crédito do pacote não encontrado",
            )

        if credit.used_qty <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nenhum crédito foi consumido para este serviço ainda",
            )

        credit.used_qty -= 1
        db.add(credit)

        usage = ClientPackageUsage(
            tenant_id=tenant_id,
            client_package_id=credit.client_package_id,
            credit_id=credit.id,
            change_qty=-1,
            notes=notes or "Estorno manual",
            user_id=user_id,
        )
        db.add(usage)

        client_pkg = credit.client_package
        if not client_pkg.is_active:
            client_pkg.is_active = True
            db.add(client_pkg)

        db.commit()
        db.refresh(credit)
        return credit

    def get_usages(
        self, db: Session, tenant_id: int, client_package_id: int
    ) -> list[ClientPackageUsage]:
        from sqlalchemy.orm import joinedload
        return (
            db.query(ClientPackageUsage)
            .options(joinedload(ClientPackageUsage.user))
            .filter(
                ClientPackageUsage.client_package_id == client_package_id,
                ClientPackageUsage.tenant_id == tenant_id,
            )
            .order_by(ClientPackageUsage.created_at.desc())
            .all()
        )

    def transfer_package(
        self,
        db: Session,
        tenant_id: int,
        client_package_id: int,
        new_pet_id: int,
    ) -> ClientPackage:
        client_pkg = (
            db.query(ClientPackage)
            .filter(
                ClientPackage.id == client_package_id,
                ClientPackage.tenant_id == tenant_id,
            )
            .first()
        )
        if not client_pkg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pacote do cliente não encontrado",
            )

        new_pet = (
            db.query(Pet)
            .filter(
                Pet.id == new_pet_id,
                Pet.tenant_id == tenant_id,
                Pet.client_id == client_pkg.client_id,
            )
            .first()
        )
        if not new_pet:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Novo pet não encontrado ou pertence a outro cliente/tutor",
            )

        client_pkg.pets = [new_pet]
        db.add(client_pkg)
        db.commit()
        db.refresh(client_pkg)
        return client_pkg

