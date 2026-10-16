from fastapi import HTTPException
from sqlalchemy.orm import Session


from app.modules.tenant_services.constants import DEFAULT_SERVICES
from app.modules.tenant_services.schemas import ServiceCreate

from .repository import ServiceRepository

class ServiceService:
    def __init__(self):
        self.repo = ServiceRepository()

    def _validate_conflicts(
        self,
        db: Session,
        tenant_id: int,
        name: str,
        species: list[str] | None,
        sizes: list[str] | None,
        coat_types: list[str] | None,
        exclude_service_id: int | None = None,
    ):
        existing_services = self.repo.get_by_name(db, tenant_id, name)
        
        COAT_LABELS = {
            "short": "Curta",
            "medium": "Média",
            "long": "Longa",
            "double": "Dupla",
            "hairless": "Sem Pelo",
        }

        for existing in existing_services:
            if exclude_service_id and existing.id == exclude_service_id:
                continue

            # 1. Sobreposição de Espécie:
            # Se algum dos dois for None/vazio, atende todas as espécies.
            species_overlap = False
            overlapping_species = []
            if not species or not existing.species:
                species_overlap = True
                overlapping_species = species or existing.species or []
            else:
                common_species = set(species) & set(existing.species)
                if common_species:
                    species_overlap = True
                    overlapping_species = sorted(list(common_species))

            if not species_overlap:
                continue

            # 2. Sobreposição de Porte:
            # Se algum dos dois for None/vazio, atende todos os portes.
            size_overlap = False
            overlapping_sizes = []
            if not sizes or not existing.sizes:
                size_overlap = True
                overlapping_sizes = sizes or existing.sizes or []
            else:
                common_sizes = set(sizes) & set(existing.sizes)
                if common_sizes:
                    size_overlap = True
                    overlapping_sizes = sorted(list(common_sizes))

            if not size_overlap:
                continue

            # 3. Sobreposição de Pelagem:
            # Se algum dos dois for None/vazio, atende todas as pelagens.
            coat_overlap = False
            overlapping_coats = []
            if not coat_types or not existing.coat_types:
                coat_overlap = True
                overlapping_coats = coat_types or existing.coat_types or []
            else:
                common_coats = set(coat_types) & set(existing.coat_types)
                if common_coats:
                    coat_overlap = True
                    overlapping_coats = sorted(list(common_coats))

            if not coat_overlap:
                continue

            # Conflito detectado em todas as 3 dimensões! Montar mensagem clara:
            details = []
            if overlapping_sizes:
                details.append(f"porte {', '.join(overlapping_sizes)}")
            else:
                details.append("todos os portes")

            extras = []
            if overlapping_species:
                extras.append(f"Espécie: {', '.join(overlapping_species)}")
            if overlapping_coats:
                friendly_coats = [COAT_LABELS.get(c, c) for c in overlapping_coats]
                extras.append(f"Pelagem: {', '.join(friendly_coats)}")

            extra_str = f" ({', '.join(extras)})" if extras else ""
            detail_msg = f"Já existe um serviço com o nome '{name.strip()}' cadastrado para o {', '.join(details)}{extra_str}."

            raise HTTPException(
                status_code=400,
                detail=detail_msg,
            )

    def create(self, db, tenant_id, data: ServiceCreate):
        self._validate_conflicts(
            db,
            tenant_id=tenant_id,
            name=data.name,
            species=data.species,
            sizes=data.sizes,
            coat_types=data.coat_types,
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
        
        # Se algum campo identificador mudar, validar conflito
        if any(v is not None for v in [data.name, data.species, data.sizes, data.coat_types]):
            new_name = data.name if data.name is not None else service.name
            new_species = data.species if data.species is not None else service.species
            new_sizes = data.sizes if data.sizes is not None else service.sizes
            new_coats = data.coat_types if data.coat_types is not None else service.coat_types
            
            self._validate_conflicts(
                db,
                tenant_id=tenant_id,
                name=new_name,
                species=new_species,
                sizes=new_sizes,
                coat_types=new_coats,
                exclude_service_id=service_id,
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
            "servico *", "preco *", "especie", "porte", "pelagem", "duracao_minutos", "descricao"
        ]
        ws.append(headers)
        
        # Style headers (Segoe UI, Blue color theme)
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1976D2", end_color="1976D2", fill_type="solid")
        required_header_fill = PatternFill(start_color="D32F2F", end_color="D32F2F", fill_type="solid")
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
            header_name = headers[col_idx - 1]
            if "*" in header_name:
                cell.fill = required_header_fill
            else:
                cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border

        # Exemplos ilustrativos com suporte a multi-atributos
        sample_rows = [
            ["Banho P/M Pelo Curto", "60.00", "Canino", "P, M", "Curta", 45, "Banho para cães pequenos e médios de pelo curto"],
            ["Banho Cães Grandes", "85.00", "Canino", "G, GG", "Curta, Média", 60, "Banho para portes grandes e gigantes"],
            ["Banho Pelagem Longa", "75.00", "Canino", "P, M", "Longa, Dupla", 60, "Banho especial para pelos longos e duplos"],
            ["Tosa Higiênica Geral", "45.00", "Canino, Felino", "PP, P, M, G, GG", "", 30, "Tosa higiênica (qualquer pelagem)"],
            ["Banho Felino", "70.00", "Felino", "", "", 45, "Banho para gatos (porte e pelagem livres)"],
            ["Corte de Unhas", "25.00", "", "", "", 15, "Corte de unhas (espécie, porte e pelagem livres)"],
        ]

        for row_data in sample_rows:
            ws.append(row_data)

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
                if col_idx == 2: # price
                    cell.number_format = "#,##0.00"
                elif col_idx == 6: # duration
                    cell.number_format = "#,##0"

        # Data Validations (Dropdowns que auxiliam a escolha sem bloquear múltiplos valores separados por vírgula)
        # 1. Species (Column 3)
        dv_species = DataValidation(type="list", formula1='"Canino,Felino,Exotico"', allow_blank=True)
        dv_species.showErrorMessage = False
        dv_species.prompt = "Escolha da lista ou digite vários separados por vírgula (ex: Canino, Felino). Vazio = Todas."
        dv_species.promptTitle = "Espécies"
        ws.add_data_validation(dv_species)
        dv_species.add(f"C2:C{ws.max_row + 200}")
        
        # 2. Sizes (Column 4)
        dv_sizes = DataValidation(type="list", formula1='"PP,P,M,G,GG"', allow_blank=True)
        dv_sizes.showErrorMessage = False
        dv_sizes.prompt = "Escolha da lista ou digite vários separados por vírgula (ex: P, M, G). Vazio = Todos."
        dv_sizes.promptTitle = "Portes"
        ws.add_data_validation(dv_sizes)
        dv_sizes.add(f"D2:D{ws.max_row + 200}")

        # 3. Coat Types (Column 5)
        dv_coats = DataValidation(type="list", formula1='"Curta,Média,Longa,Dupla,Sem Pelo"', allow_blank=True)
        dv_coats.showErrorMessage = False
        dv_coats.prompt = "Escolha da lista ou digite várias separadas por vírgula (ex: Curta, Longa). Vazio = Todas."
        dv_coats.promptTitle = "Pelagens"
        ws.add_data_validation(dv_coats)
        dv_coats.add(f"E2:E{ws.max_row + 200}")

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

    async def import_services_from_excel(self, db: Session, tenant_id: int, file_content: bytes, progress_callback=None):
        import openpyxl
        import io
        from app.modules.tenant_services.models import Service

        if not file_content:
            return {"created": 0, "updated": 0, "total": 0, "errors": ["Arquivo de planilha vazio"]}

        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
            ws = wb.active
        except Exception as e:
            return {"created": 0, "updated": 0, "total": 0, "errors": [f"Erro ao ler arquivo Excel: {str(e)}"]}

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return {"created": 0, "updated": 0, "total": 0, "errors": ["A planilha está vazia"]}

        raw_headers = rows[0]
        headers = []
        for h in raw_headers:
            if h is None:
                headers.append("")
            else:
                h_str = str(h).strip().lower().replace("*", "").strip()
                if h_str in ("nome", "serviço", "nome_servico", "nome_do_servico"):
                    h_str = "servico"
                elif h_str in ("preço", "valor", "preco_venda"):
                    h_str = "preco"
                elif h_str in ("duração", "duracao", "tempo"):
                    h_str = "duracao_minutos"
                headers.append(h_str)

        required_cols = ["servico", "preco"]
        missing_cols = [col for col in required_cols if col not in headers]
        if missing_cols:
            return {
                "created": 0, "updated": 0, "total": 0,
                "errors": [f"Colunas obrigatórias ausentes na planilha: {', '.join(missing_cols)}"]
            }


        non_empty_rows = [
            rv for rv in rows[1:]
            if any(v is not None and str(v).strip() != "" for v in rv)
        ]
        total_rows = len(non_empty_rows)

        if progress_callback and total_rows > 0:
            progress_callback(0, total_rows, 0, 0)

        # Pre-fetch existing services (1 query)
        existing_services_q = db.query(Service).filter(Service.tenant_id == tenant_id).all()
        existing_services: dict[tuple, Service] = {
            (
                s.name.lower().strip(),
                tuple(sorted((s.species or []))),
                tuple(sorted((s.sizes or []))),
                tuple(sorted((s.coat_types or []))),
            ): s for s in existing_services_q
        }

        created_count = 0
        updated_count = 0
        processed_count = 0
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

        import re

        def parse_species(val):
            if val is None or str(val).strip() == "":
                return None
            res = []
            for item in re.split(r"[,;/&]|\se\s", str(val)):
                cleaned = item.strip().lower()
                if not cleaned:
                    continue
                if cleaned in ("todos", "todas", "qualquer", "todas as espécies", "todos os animais"):
                    return None
                if "canino" in cleaned or "cão" in cleaned or "cao" in cleaned or "cachorro" in cleaned:
                    if "Canino" not in res: res.append("Canino")
                elif "felino" in cleaned or "gato" in cleaned:
                    if "Felino" not in res: res.append("Felino")
                elif "exotico" in cleaned or "exótico" in cleaned:
                    if "Exotico" not in res: res.append("Exotico")
            return res if res else None

        def parse_sizes(val):
            if val is None or str(val).strip() == "":
                return None
            res = []
            for item in re.split(r"[,;/&]|\se\s", str(val)):
                item_cleaned = item.strip()
                v = item_cleaned.lower()
                if not v:
                    continue
                if v in ("todos", "todas", "qualquer", "todos os portes", "qualquer porte"):
                    return None
                if v in ["pp", "mini", "micro"] or "(pp)" in v:
                    if "PP" not in res: res.append("PP")
                elif v in ["p", "pequeno", "peq"] or "(p)" in v:
                    if "P" not in res: res.append("P")
                elif v in ["m", "medio", "médio"] or "(m)" in v:
                    if "M" not in res: res.append("M")
                elif v in ["g", "grande"] or "(g)" in v:
                    if "G" not in res: res.append("G")
                elif v in ["gg", "gigante", "extra grande"] or "(gg)" in v:
                    if "GG" not in res: res.append("GG")
                elif item_cleaned.upper() in ["PP", "P", "M", "G", "GG"]:
                    if item_cleaned.upper() not in res: res.append(item_cleaned.upper())
            return res if res else None

        def parse_coat_types(val):
            if val is None or str(val).strip() == "":
                return None
            res = []
            coat_map = {
                "curta": "short", "curto": "short", "short": "short",
                "média": "medium", "media": "medium", "médio": "medium", "medio": "medium", "medium": "medium",
                "longa": "long", "longo": "long", "long": "long",
                "dupla": "double", "duplo": "double", "double": "double",
                "sem pelo": "hairless", "sem pelagem": "hairless", "hairless": "hairless"
            }
            for item in re.split(r"[,;/&]|\se\s", str(val)):
                cleaned = item.strip().lower()
                if not cleaned:
                    continue
                if cleaned in ("todas", "todos", "qualquer", "todas as pelagens"):
                    return None
                mapped = coat_map.get(cleaned)
                if mapped and mapped not in res:
                    res.append(mapped)
            return res if res else None

        CHUNK_SIZE = 200
        new_services: list[Service] = []

        def _flush_chunk():
            nonlocal new_services
            if new_services:
                db.add_all(new_services)
                db.flush()
                new_services = []
            db.commit()

        for row_idx, row_values in enumerate(non_empty_rows, start=2):
            try:
                row = {h: val for h, val in zip(headers, row_values) if h}

                servico = clean_str(row.get("servico"))
                if not servico:
                    raise ValueError("Nome do serviço é obrigatório")

                especie_val = clean_str(row.get("especie"))
                especie = parse_species(especie_val) if especie_val else None

                porte_val = clean_str(row.get("porte"))
                porte = parse_sizes(porte_val) if porte_val else None

                coat_val = clean_str(row.get("pelagem"))
                coat_type = parse_coat_types(coat_val)

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

                key = (
                    servico.lower().strip(),
                    tuple(sorted(especie or [])),
                    tuple(sorted(porte or [])),
                    tuple(sorted(coat_type or [])),
                )

                service_obj = existing_services.get(key)
                if not service_obj:
                    service_obj = Service(
                        tenant_id=tenant_id,
                        name=servico,
                        description=desc,
                        species=especie,
                        sizes=porte,
                        coat_types=coat_type,
                        price_cents=price_cents,
                        duration_minutes=duration_minutes,
                        is_active=True
                    )
                    new_services.append(service_obj)
                    existing_services[key] = service_obj
                    created_count += 1
                else:
                    _changed = False
                    for attr, val in [
                        ("price_cents", price_cents),
                        ("duration_minutes", duration_minutes),
                        ("description", desc),
                    ]:
                        if val is not None and getattr(service_obj, attr, None) != val:
                            setattr(service_obj, attr, val)
                            _changed = True
                    if _changed:
                        updated_count += 1

                processed_count += 1

            except Exception as e:
                errors.append(f"Linha {row_idx}: {str(e)}")

            if (row_idx - 1) % CHUNK_SIZE == 0:
                _flush_chunk()
                if progress_callback and total_rows > 0:
                    pct = min(int((row_idx - 1) / total_rows * 100), 99)
                    progress_callback(row_idx - 1, total_rows, processed_count, pct)

        _flush_chunk()

        return {
            "created": created_count,
            "updated": updated_count,
            "total": total_rows,
            "errors": errors,
        }

    async def import_services_from_excel_background(
        self,
        job_id: str,
        tenant_id: int,
        file_content: bytes,
    ) -> None:
        from app.modules.clients.import_jobs import update_job
        from app.config.database import SessionLocal

        db = SessionLocal()
        try:
            update_job(job_id, status="running", progress=0)

            def _on_progress(processed: int, total: int, count: int, pct: int):
                update_job(job_id, progress=pct, imported=count, total=total)

            result = await self.import_services_from_excel(
                db, tenant_id, file_content,
                progress_callback=_on_progress,
            )
            update_job(
                job_id,
                status="done",
                progress=100,
                created=result["created"],
                updated=result["updated"],
                total=result.get("total", 0),
                errors=result["errors"],
            )
        except Exception as e:
            update_job(job_id, status="error", errors=[str(e)])
        finally:
            db.close()

    def export_to_excel(self, db: Session, tenant_id: int) -> bytes:
        import openpyxl
        from openpyxl.styles import Font, PatternFill
        from io import BytesIO

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Serviços"
        
        headers = [
            "ID", "Nome do Serviço", "Espécie", "Porte", "Pelagem", "Duração (min)", "Preço", "Descrição", "Ativo"
        ]
        ws.append(headers)
        
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1976D2", end_color="1976D2", fill_type="solid")
        
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill

        services = self.repo.list(db, tenant_id)
        
        coat_map = {
            "short": "Curta",
            "medium": "Média",
            "long": "Longa",
            "double": "Dupla",
            "hairless": "Sem Pelo"
        }
        for s in services:
            species_val = ", ".join(s.species) if s.species else "Todos"
            size_val = ", ".join(s.sizes) if s.sizes else "Todos"
            coat_val = ", ".join(coat_map.get(c, c) for c in s.coat_types) if s.coat_types else "Todos"
            
            ws.append([
                s.id, s.name, species_val, size_val, coat_val,
                s.duration_minutes or "", float(s.price_cents) / 100 if s.price_cents else 0.0,
                s.description or "", "Sim" if s.is_active else "Não"
            ])
                
        out = BytesIO()
        wb.save(out)
        return out.getvalue()
