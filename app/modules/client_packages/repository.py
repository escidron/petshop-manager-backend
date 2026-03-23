from sqlalchemy.orm import Session, selectinload
from .models import ClientPackage, ClientPackageCredit


class ClientPackageRepository:
    def create(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        pet_id: int,
        package_id: int,
        package_name: str,
        credits_data: list[dict],
    ) -> ClientPackage:
        client_package = ClientPackage(
            tenant_id=tenant_id,
            client_id=client_id,
            pet_id=pet_id,
            package_id=package_id,
            package_name=package_name,
        )
        db.add(client_package)
        db.flush()

        for credit in credits_data:
            db.add(
                ClientPackageCredit(
                    client_package_id=client_package.id,
                    service_id=credit["service_id"],
                    service_name=credit["service_name"],
                    total_qty=credit["total_qty"],
                    used_qty=0,
                )
            )

        db.commit()
        db.refresh(client_package)
        return self.get_by_id(db, client_package.id)

    def get_by_id(self, db: Session, client_package_id: int) -> ClientPackage | None:
        return (
            db.query(ClientPackage)
            .options(selectinload(ClientPackage.credits))
            .filter(ClientPackage.id == client_package_id)
            .first()
        )

    def get_by_id_scoped(
        self, db: Session, tenant_id: int, client_package_id: int
    ) -> ClientPackage | None:
        return (
            db.query(ClientPackage)
            .options(selectinload(ClientPackage.credits))
            .filter(
                ClientPackage.id == client_package_id,
                ClientPackage.tenant_id == tenant_id,
            )
            .first()
        )

    def list_by_pet(
        self, db: Session, tenant_id: int, pet_id: int
    ) -> list[ClientPackage]:
        return (
            db.query(ClientPackage)
            .options(selectinload(ClientPackage.credits))
            .filter(
                ClientPackage.tenant_id == tenant_id,
                ClientPackage.pet_id == pet_id,
                ClientPackage.is_active == True,
            )
            .order_by(ClientPackage.created_at)
            .all()
        )

    def list_by_client(
        self, db: Session, tenant_id: int, client_id: int
    ) -> list[ClientPackage]:
        return (
            db.query(ClientPackage)
            .options(selectinload(ClientPackage.credits))
            .filter(
                ClientPackage.tenant_id == tenant_id,
                ClientPackage.client_id == client_id,
            )
            .order_by(ClientPackage.created_at.desc())
            .all()
        )

    def deactivate(self, db: Session, client_package: ClientPackage) -> ClientPackage:
        client_package.is_active = False
        db.add(client_package)
        db.commit()
        db.refresh(client_package)
        return client_package

    def find_active_credit(
        self, db: Session, tenant_id: int, pet_id: int, service_id: int
    ) -> ClientPackageCredit | None:
        """Busca o crédito mais antigo disponível para um pet/serviço (FIFO)."""
        return (
            db.query(ClientPackageCredit)
            .join(ClientPackage)
            .filter(
                ClientPackage.pet_id == pet_id,
                ClientPackage.tenant_id == tenant_id,
                ClientPackage.is_active == True,
                ClientPackageCredit.service_id == service_id,
                ClientPackageCredit.used_qty < ClientPackageCredit.total_qty,
            )
            .order_by(ClientPackage.created_at)
            .first()
        )

    def consume_credit(
        self, db: Session, credit: ClientPackageCredit
    ) -> None:
        credit.used_qty += 1
        db.add(credit)
        # Verifica se todos os créditos do pacote foram usados
        client_pkg = credit.client_package
        db.refresh(client_pkg, ["credits"])
        if all(c.used_qty >= c.total_qty for c in client_pkg.credits):
            client_pkg.is_active = False
            db.add(client_pkg)
