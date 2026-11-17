import io
import os
from fastapi import HTTPException, status
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.modules.clients.repository import ClientRepository
from app.services.gcs_service import GCSService
from app.utils.timezone import get_brazil_now, to_brazil_datetime
from .models import PetPhoto
from .repository import PetRepository
from .schemas import (
    ClientPetReportItem,
    ClientPetReportResponse,
    PetCreate,
    PetUpdate,
)

SPECIES_MAP = {
    "dog": "Canino",
    "canino": "Canino",
    "cat": "Felino",
    "felino": "Felino",
    "bird": "Ave",
    "ave": "Ave",
    "fish": "Peixe",
    "peixe": "Peixe",
    "reptile": "Réptil",
    "réptil": "Réptil",
    "rodent": "Roedor",
    "roedor": "Roedor",
    "other": "Outros",
    "outro": "Outros",
    "outros": "Outros",
}

GENDER_MAP = {
    "male": "Macho",
    "macho": "Macho",
    "female": "Fêmea",
    "femea": "Fêmea",
    "fêmea": "Fêmea",
    "other": "Outro",
    "outro": "Outro",
    "unknown": "Não informado",
}

COAT_MAP = {
    "short": "Curta",
    "curta": "Curta",
    "medium": "Média",
    "media": "Média",
    "média": "Média",
    "long": "Longa",
    "longa": "Longa",
    "hairless": "Sem Pelo",
    "sem pelo": "Sem Pelo",
    "sem_pelo": "Sem Pelo",
    "double": "Dupla",
    "dupla": "Dupla",
    "curly": "Encaracolada",
    "encaracolada": "Encaracolada",
}

AGE_UNIT_MAP = {
    "months": "Meses",
    "meses": "Meses",
    "years": "Anos",
    "anos": "Anos",
}



class PetService:
    def __init__(self):
        self.repository = PetRepository()
        self.client_repository = ClientRepository()

    def create_pet(
        self,
        db: Session,
        tenant_id: int,
        data: PetCreate,
    ):
        client = self.client_repository.get_by_id(
            db, tenant_id, data.client_id
        )
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cliente não encontrado",
            )

        return self.repository.create(db, tenant_id, data)

    def get_pet(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
    ):
        pet = self.repository.get_by_id(
            db, tenant_id, pet_id
        )
        if not pet:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pet não encontrado",
            )
        return pet

    def list_pets(self, db: Session, tenant_id: int):
        return self.repository.list_pets(db, tenant_id)
    
    def list_pets_by_client(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        include_photos: bool = True,
    ):
        pets = self.repository.list_by_client(
            db, tenant_id, client_id, include_photos=include_photos
        )
        if not include_photos:
            for pet in pets:
                pet.__dict__["photos"] = []
        return pets

    def update_pet(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
        data: PetUpdate,
    ):
        pet = self.get_pet(db, tenant_id, pet_id)
        return self.repository.update(db, pet, data)

    def delete_pet(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
    ):
        pet = self.get_pet(db, tenant_id, pet_id)
        self.repository.delete(db, pet)

    def add_pet_photo(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
        file_content: bytes,
        filename: str,
        content_type: str,
        is_profile: bool,
        category: str,
    ):
        # 1. Garante que o pet existe e pertence ao tenant
        self.get_pet(db, tenant_id, pet_id)

        # 2. Gera um nome de arquivo único
        import uuid
        ext = os.path.splitext(filename)[1] or ".jpg"
        unique_filename = f"pets/{pet_id}/{uuid.uuid4()}{ext}"

        # 3. Faz upload no GCS
        from app.services.gcs_service import GCSService
        gcs = GCSService()
        photo_url = gcs.upload_file(file_content, unique_filename, content_type)

        # 4. Se for foto de perfil, desmarca as outras
        if is_profile:
            db.query(PetPhoto).filter(PetPhoto.pet_id == pet_id, PetPhoto.tenant_id == tenant_id).update({"is_profile": False})

        # 5. Salva no banco de dados
        new_photo = PetPhoto(
            tenant_id=tenant_id,
            pet_id=pet_id,
            photo_url=photo_url,
            is_profile=is_profile,
            category=category
        )
        db.add(new_photo)
        db.commit()
        db.refresh(new_photo)
        return new_photo

    def delete_pet_photo(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
        photo_id: int,
    ):
        # Garante que o pet pertence ao tenant
        self.get_pet(db, tenant_id, pet_id)

        photo = db.query(PetPhoto).filter(
            PetPhoto.id == photo_id,
            PetPhoto.pet_id == pet_id,
            PetPhoto.tenant_id == tenant_id
        ).first()
        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Foto não encontrada",
            )

        # Remove do GCS
        gcs = GCSService()
        bucket_prefix = f"https://storage.googleapis.com/{gcs.bucket_name}/"
        if photo.photo_url.startswith(bucket_prefix):
            blob_name = photo.photo_url[len(bucket_prefix):]
            try:
                gcs.delete_file(blob_name)
            except Exception as e:
                # Loga o erro mas deleta do banco para não ficar órfão
                print(f"Erro ao deletar arquivo do GCS: {e}")

        db.delete(photo)
        db.commit()

    def set_profile_photo(
        self,
        db: Session,
        tenant_id: int,
        pet_id: int,
        photo_id: int,
    ):
        self.get_pet(db, tenant_id, pet_id)

        photo = db.query(PetPhoto).filter(
            PetPhoto.id == photo_id,
            PetPhoto.pet_id == pet_id,
            PetPhoto.tenant_id == tenant_id
        ).first()
        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Foto não encontrada",
            )

        db.query(PetPhoto).filter(PetPhoto.pet_id == pet_id, PetPhoto.tenant_id == tenant_id).update({"is_profile": False})
        photo.is_profile = True
        db.commit()
        db.refresh(photo)
        return photo

    def get_clients_pets_report(
        self,
        db: Session,
        tenant_id: int,
        is_active: bool | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ClientPetReportResponse:
        query = self.repository.get_clients_pets_query(
            db, tenant_id, is_active=is_active, search=search
        )
        total = query.count()
        total_active_pets, total_unique_clients = self.repository.get_report_counts(db, tenant_id)

        pets = query.offset(offset).limit(limit).all()
        pet_ids = [p.id for p in pets]
        last_services_map = self.repository.get_last_services_map(db, tenant_id, pet_ids)

        items: list[ClientPetReportItem] = []
        for p in pets:
            last_info = last_services_map.get(p.id)
            species_clean = p.species.lower().strip() if p.species else ""
            gender_clean = p.gender.lower().strip() if p.gender else ""
            coat_clean = p.coat_type.lower().strip() if p.coat_type else ""
            age_unit_clean = p.age_unit.lower().strip() if p.age_unit else ""

            species_label = SPECIES_MAP.get(species_clean, p.species or "Outros")
            gender_label = GENDER_MAP.get(gender_clean, "Não informado")
            coat_label = COAT_MAP.get(coat_clean, p.coat_type) if p.coat_type else None
            age_unit_label = AGE_UNIT_MAP.get(age_unit_clean, p.age_unit) if p.age_unit else None

            items.append(
                ClientPetReportItem(
                    pet_id=p.id,
                    pet_name=p.name,
                    species=p.species,
                    species_label=species_label,
                    breed=p.breed,
                    gender=p.gender,
                    gender_label=gender_label,
                    size=p.size,
                    coat_type=p.coat_type,
                    coat_type_label=coat_label,
                    coat_color=p.coat_color,
                    is_neutered=p.is_neutered,
                    age=p.age,
                    age_unit=p.age_unit,
                    age_unit_label=age_unit_label,
                    birth_date=p.birth_date,
                    is_active=p.is_active,
                    is_deceased=p.is_deceased,
                    notes=p.notes,
                    client_id=p.client.id if p.client else 0,
                    client_name=p.client.name if p.client else "Sem Dono",
                    client_phone=p.client.phone if p.client else None,
                    client_phone_secondary=p.client.phone_secondary if p.client else None,
                    last_service_date=last_info["scheduled_at"] if last_info else None,
                    last_service_name=last_info["service_name"] if last_info else None,
                )
            )

        return ClientPetReportResponse(
            items=items,
            total=total,
            total_active_pets=total_active_pets,
            total_unique_clients=total_unique_clients,
        )

    def export_clients_pets_excel(
        self,
        db: Session,
        tenant_id: int,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> bytes:
        query = self.repository.get_clients_pets_query(
            db, tenant_id, is_active=is_active, search=search
        )
        pets = query.all()
        pet_ids = [p.id for p in pets]
        last_services_map = self.repository.get_last_services_map(db, tenant_id, pet_ids)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Clientes & Pets"

        header_fill = PatternFill(start_color="313485", end_color="313485", fill_type="solid")
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")

        sub_fill_even = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        sub_fill_odd = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

        data_font = Font(name="Segoe UI", size=10, color="0F172A")
        bold_font = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
        active_font = Font(name="Segoe UI", size=10, bold=True, color="166534")
        inactive_font = Font(name="Segoe UI", size=10, color="64748B")

        thin_border = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0"),
        )

        headers = [
            "Cliente (Dono)",
            "Telefone",
            "Telefone Secundário",
            "Nome do Pet",
            "Espécie",
            "Raça",
            "Sexo",
            "Porte",
            "Pelagem",
            "Cor",
            "Castrado",
            "Data de Nascimento",
            "Idade",
            "Status",
            "Falecido",
            "Data do Último Serviço",
            "Último Serviço Realizado",
            "Observações",
        ]

        # Linha 1: Título
        ws.merge_cells("A1:R1")
        title_cell = ws["A1"]
        title_cell.value = "RELATÓRIO DE CLIENTES & PETS"
        title_cell.font = Font(name="Segoe UI", size=14, bold=True, color="1E293B")
        title_cell.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 28

        # Linha 2: Metadados
        now_br = get_brazil_now().strftime("%d/%m/%Y às %H:%M")
        ws.merge_cells("A2:R2")
        meta_cell = ws["A2"]
        meta_cell.value = f"Gerado em: {now_br} | Total de pets no relatório: {len(pets)}"
        meta_cell.font = Font(name="Segoe UI", size=9, italic=True, color="64748B")
        meta_cell.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[2].height = 20

        # Linha 4: Cabeçalhos
        ws.row_dimensions[4].height = 26
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=4, column=col_idx, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(
                horizontal="center" if col_idx not in (1, 4, 6, 17, 18) else "left",
                vertical="center",
            )
            cell.border = thin_border

        # Linhas de Dados
        for row_idx, p in enumerate(pets, start=5):
            ws.row_dimensions[row_idx].height = 21
            fill = sub_fill_even if row_idx % 2 == 0 else sub_fill_odd

            last_info = last_services_map.get(p.id)
            last_date_str = ""
            last_service_str = ""
            if last_info:
                dt_br = to_brazil_datetime(last_info["scheduled_at"])
                last_date_str = dt_br.strftime("%d/%m/%Y %H:%M") if dt_br else ""
                last_service_str = last_info["service_name"]

            species_clean = p.species.lower().strip() if p.species else ""
            gender_clean = p.gender.lower().strip() if p.gender else ""
            coat_clean = p.coat_type.lower().strip() if p.coat_type else ""
            age_unit_clean = p.age_unit.lower().strip() if p.age_unit else ""

            species_val = SPECIES_MAP.get(species_clean, p.species or "Outros")
            gender_val = GENDER_MAP.get(gender_clean, "Não informado")
            coat_val = COAT_MAP.get(coat_clean, p.coat_type or "Não informada")
            age_unit_val = AGE_UNIT_MAP.get(age_unit_clean, p.age_unit or "")
            age_str = f"{p.age} {age_unit_val}".strip() if p.age else "Não informada"
            size_val = f"Porte {p.size}" if p.size else "Não informado"

            row_values = [
                p.client.name if p.client else "",
                p.client.phone if p.client else "",
                p.client.phone_secondary or "" if p.client else "",
                p.name,
                species_val,
                p.breed or "Não informada",
                gender_val,
                size_val,
                coat_val,
                p.coat_color or "Não informada",
                "Sim" if p.is_neutered else ("Não" if p.is_neutered is False else "Não informado"),
                p.birth_date.strftime("%d/%m/%Y") if p.birth_date else "Não informada",
                age_str,
                "Ativo" if p.is_active else "Inativo",
                "Sim" if p.is_deceased else "Não",
                last_date_str if last_date_str else "Sem atendimentos",
                last_service_str if last_service_str else "Nenhum",
                p.notes or "",
            ]

            for col_idx, val in enumerate(row_values, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.fill = fill
                cell.border = thin_border

                if col_idx in (1, 4):
                    cell.font = bold_font
                elif col_idx == 14:
                    cell.font = active_font if val == "Ativo" else inactive_font
                else:
                    cell.font = data_font

                if col_idx in (2, 3, 5, 7, 8, 11, 12, 13, 14, 15, 16):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

        ws.freeze_panes = "A5"

        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.row < 4:
                    continue
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()

