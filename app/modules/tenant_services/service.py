from fastapi import HTTPException
from sqlalchemy.orm import Session


from app.modules.tenant_services.constants import DEFAULT_SERVICES
from app.modules.tenant_services.schemas import ServiceCreate

from .repository import ServiceRepository

class ServiceService:
    def __init__(self):
        self.repo = ServiceRepository()

    def create(self, db, tenant_id, data: ServiceCreate):
        # Validar duplicidade
        existing = self.repo.get_by_attributes(
            db,
            tenant_id=tenant_id,
            name=data.name,
            species=data.species,
            size=data.size,
            coat_type=data.coat_type
        )
        if existing:
                raise HTTPException(
                    status_code=400,
                    detail="Já existe um serviço com este nome e as mesmas variações (Espécie, Porte, Pelagem). Para preços diferentes, especifique as variações correspondentes."
                )
            
        return self.repo.create(db, tenant_id, data)

    def list(self, db, tenant_id):
        return self.repo.list(db, tenant_id)

    def get(self, db, tenant_id, service_id):
        service = self.repo.get_by_id(
            db, tenant_id, service_id
        )
        if not service:
            raise HTTPException(404, "Serviço não encontrado")
        return service

    def update(self, db, tenant_id, service_id, data):
        service = self.get(db, tenant_id, service_id)
        
        # Se algum campo identificador mudar, validar duplicidade
        if any(v is not None for v in [data.name, data.species, data.size, data.coat_type]):
            new_name = data.name if data.name is not None else service.name
            new_species = data.species if data.species is not None else service.species
            new_size = data.size if data.size is not None else service.size
            new_coat = data.coat_type if data.coat_type is not None else service.coat_type
            
            existing = self.repo.get_by_attributes(
                db,
                tenant_id=tenant_id,
                name=new_name,
                species=new_species,
                size=new_size,
                coat_type=new_coat
            )
            
            if existing and existing.id != service_id:
                raise HTTPException(
                    status_code=400,
                    detail="Já existe um serviço cadastrado com este nome e variações."
                )

        return self.repo.update(db, service, data)

    def delete(self, db, tenant_id, service_id):
        service = self.get(db, tenant_id, service_id)
        self.repo.delete(db, service)

    def create_default_services(
        self,
        db,
        tenant_id: int,
    ):
        for service in DEFAULT_SERVICES:
            data = ServiceCreate(**service)
            self.repo.create(
                db,
                tenant_id=tenant_id,
                data=data,
            )

    def generate_import_template_excel(self) -> bytes:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.worksheet.datavalidation import DataValidation
        from io import BytesIO
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Serviços"
        
        # Add headers
        headers = [
            "servico *", "especie", "porte", "pelagem", "preco *", "duracao_minutos", "descricao"
        ]
        ws.append(headers)
        
        # Style headers (Segoe UI, Blue color theme)
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1976D2", end_color="1976D2", fill_type="solid")
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        left_align = Alignment(horizontal="left", vertical="center")
        
        thin_border = Border(
            left=Side(style="thin", color="D3D3D3"),
            right=Side(style="thin", color="D3D3D3"),
            top=Side(style="thin", color="D3D3D3"),
            bottom=Side(style="thin", color="D3D3D3")
        )
        
        # Format header row
        ws.row_dimensions[1].height = 28
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border

        base_services = ["Banho", "Tosa", "Banho & Tosa"]
        species_list = ["Canino", "Felino"]
        sizes_list = ["PP", "P", "M", "G", "GG"]
        coat_types = [None, "Curta", "Média", "Longa", "Dupla"]
        size_descriptions = {
            "PP": "porte muito pequeno (PP)",
            "P": "porte pequeno (P)",
            "M": "porte médio (M)",
            "G": "porte grande (G)",
            "GG": "porte muito grande (GG)"
        }

        # Append predefined rows
        for service in base_services:
            for species in species_list:
                for size in sizes_list:
                    for coat in coat_types:
                        size_desc = size_descriptions[size]
                        if coat:
                            desc = f"{service} para animal {species.lower()} de {size_desc} com pelagem {coat.lower()}"
                        else:
                            desc = f"{service} para animal {species.lower()} de {size_desc}"
                        
                        row = [
                            service,
                            species,
                            size,
                            coat,  # pelagem
                            None,  # preco (deixar em branco)
                            None,  # duracao (deixar em branco)
                            desc   # descricao
                        ]
                        ws.append(row)

        # Format rows (starting at row 2 up to ws.max_row)
        for r_idx in range(2, ws.max_row + 1):
            ws.row_dimensions[r_idx].height = 20
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=r_idx, column=col_idx)
                cell.font = Font(name="Segoe UI", size=10)
                cell.border = thin_border
                
                # Alignments & formatting based on column
                if col_idx in [1, 7]: # service, description -> left
                    cell.alignment = left_align
                else: # species, size, coat_type, price, duration -> center
                    cell.alignment = center_align
                    
                # Number formats
                if col_idx == 5: # price
                    cell.number_format = "#,##0.00"
                elif col_idx == 6: # duration
                    cell.number_format = "#,##0"

        # Data Validations (Dropdowns)
        # 1. Species (Column B - col_idx 2)
        dv_species = DataValidation(type="list", formula1='"Canino,Felino"', allow_blank=True)
        dv_species.error = 'Escolha uma espécie da lista (Canino ou Felino)'
        dv_species.errorTitle = 'Espécie Inválida'
        dv_species.prompt = 'Selecione a espécie atendida'
        dv_species.promptTitle = 'Espécie'
        ws.add_data_validation(dv_species)
        dv_species.add(f"B2:B{ws.max_row + 100}")
        
        # 2. Sizes (Column C - col_idx 3)
        dv_sizes = DataValidation(type="list", formula1='"PP,P,M,G,GG"', allow_blank=True)
        dv_sizes.error = 'Escolha um porte da lista (PP, P, M, G ou GG)'
        dv_sizes.errorTitle = 'Porte Inválido'
        dv_sizes.prompt = 'Selecione o porte atendido'
        dv_sizes.promptTitle = 'Porte'
        ws.add_data_validation(dv_sizes)
        dv_sizes.add(f"C2:C{ws.max_row + 100}")

        # 3. Coat Types (Column D - col_idx 4)
        dv_coats = DataValidation(type="list", formula1='"Curta,Média,Longa,Dupla,Sem Pelo"', allow_blank=True)
        dv_coats.error = 'Escolha uma pelagem da lista'
        dv_coats.errorTitle = 'Pelagem Inválida'
        dv_coats.prompt = 'Selecione o tipo de pelagem (opcional)'
        dv_coats.promptTitle = 'Pelagem'
        ws.add_data_validation(dv_coats)
        dv_coats.add(f"D2:D{ws.max_row + 100}")

        # Auto-fit column widths
        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
            
        # Enable grid lines explicitly
        ws.views.sheetView[0].showGridLines = True
            
        out = BytesIO()
        wb.save(out)
        return out.getvalue()

    async def import_services_from_excel(self, db: Session, tenant_id: int, file_content: bytes):
        import openpyxl
        import io
        
        if not file_content:
            return {"imported": 0, "errors": ["Arquivo de planilha vazio"]}

        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
            ws = wb.active
        except Exception as e:
            return {"imported": 0, "errors": [f"Erro ao ler arquivo Excel: {str(e)}"]}

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return {"imported": 0, "errors": ["A planilha está vazia"]}

        # Clean headers
        raw_headers = rows[0]
        headers = []
        for h in raw_headers:
            if h is None:
                headers.append("")
            else:
                headers.append(str(h).strip().lower().replace("*", "").strip())

        required_cols = ["servico", "especie", "porte", "preco", "duracao_minutos"]
        missing_cols = [col for col in required_cols if col not in headers]
        if missing_cols:
            return {
                "imported": 0,
                "errors": [f"Colunas obrigatórias ausentes na planilha: {', '.join(missing_cols)}"]
            }

        imported_count = 0
        errors = []

        def parse_money(val):
            if val is None or str(val).strip() == "":
                return None
            if isinstance(val, (int, float)):
                return int(round(val * 100))
            try:
                cleaned = str(val).replace("R$", "").strip()
                if "," in cleaned and "." in cleaned:
                    if cleaned.rfind(",") > cleaned.rfind("."):
                        cleaned = cleaned.replace(".", "").replace(",", ".")
                    else:
                        cleaned = cleaned.replace(",", "")
                elif "," in cleaned:
                    cleaned = cleaned.replace(",", ".")
                return int(round(float(cleaned) * 100))
            except (ValueError, TypeError):
                return None

        def clean_str(val):
            if val is None or str(val).strip() == "":
                return None
            return str(val).strip()

        def parse_species(val):
            if val is None or str(val).strip() == "":
                return None
            cleaned = str(val).strip().lower()
            if "canino" in cleaned or "cão" in cleaned or "cao" in cleaned or "cachorro" in cleaned:
                return "Canino"
            if "felino" in cleaned or "gato" in cleaned:
                return "Felino"
            if "exotico" in cleaned or "exótico" in cleaned:
                return "Exoticos"
            return None

        def parse_size(val):
            if val is None or str(val).strip() == "":
                return None
            cleaned = str(val).strip().upper()
            if cleaned in ["PP", "P", "M", "G", "GG"]:
                return cleaned
            return None

        def parse_coat_type(val):
            if val is None or str(val).strip() == "":
                return None
            cleaned = str(val).strip().lower()
            coat_map = {
                "curta": "short",
                "média": "medium",
                "media": "medium",
                "longa": "long",
                "dupla": "double",
                "sem pelo": "hairless"
            }
            return coat_map.get(cleaned, None)

        for row_idx, row_values in enumerate(rows[1:], start=2):
            try:
                row = {}
                has_any_value = False
                for h, val in zip(headers, row_values):
                    if h:
                        row[h] = val
                        if val is not None and str(val).strip() != "":
                            has_any_value = True
                
                if not has_any_value:
                    continue

                servico = clean_str(row.get("servico"))
                if not servico:
                    raise ValueError("Nome do serviço é obrigatório")

                especie_val = clean_str(row.get("especie"))
                especie = None
                if especie_val:
                    especie = parse_species(especie_val)
                    if not especie:
                        raise ValueError("Espécie inválida (deve ser Canino ou Felino)")

                porte_val = clean_str(row.get("porte"))
                porte = None
                if porte_val:
                    porte = parse_size(porte_val)
                    if not porte:
                        raise ValueError("Porte inválido (deve ser PP, P, M, G ou GG)")

                coat_val = clean_str(row.get("pelagem"))
                coat_type = parse_coat_type(coat_val)

                raw_price = row.get("preco")
                price_cents = parse_money(raw_price)
                if price_cents is None:
                    raise ValueError("Preço é obrigatório e deve ser um valor válido")

                raw_duration = row.get("duracao_minutos")
                duration_minutes = None
                if raw_duration is not None and str(raw_duration).strip() != "":
                    try:
                        duration_minutes = int(float(str(raw_duration)))
                    except Exception:
                        raise ValueError("Duração em minutos deve ser um número inteiro")

                desc = clean_str(row.get("descricao"))

                data = ServiceCreate(
                    name=servico,
                    description=desc,
                    species=especie,
                    size=porte,
                    coat_type=coat_type,
                    price_cents=price_cents,
                    duration_minutes=duration_minutes,
                    is_active=True
                )
                self.create(db, tenant_id, data)
                imported_count += 1
            except Exception as e:
                errors.append(f"Linha {row_idx}: {str(e)}")

        return {"imported": imported_count, "errors": errors}