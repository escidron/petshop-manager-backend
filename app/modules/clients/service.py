from datetime import date, datetime
import io
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .repository import ClientRepository
from .schemas import ClientCreate, ClientUpdate
from app.modules.pets.repository import PetRepository
from app.modules.pets.schemas import PetCreate


class ClientService:
    def __init__(self):
        self.repository = ClientRepository()
        self.pet_repository = PetRepository()

    def create_client(
        self, db: Session, tenant_id: int, data: ClientCreate
    ):
        return self.repository.create(db, tenant_id, data)

    def get_client(
        self, db: Session, tenant_id: int, client_id: int
    ):
        client = self.repository.get_by_id(
            db, tenant_id, client_id
        )
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cliente não encontrado",
            )
        return client

    def list_clients(self, db: Session, tenant_id: int):
        return self.repository.list(db, tenant_id)

    def update_client(
        self,
        db: Session,
        tenant_id: int,
        client_id: int,
        data: ClientUpdate,
    ):
        client = self.get_client(db, tenant_id, client_id)
        return self.repository.update(db, client, data)

    def delete_client(
        self, db: Session, tenant_id: int, client_id: int
    ):
        client = self.get_client(db, tenant_id, client_id)
        self.repository.delete(db, client)

    def generate_import_template_excel(self) -> bytes:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.worksheet.datavalidation import DataValidation
        from io import BytesIO
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Clientes e Pets"
        
        # Add headers
        headers = [
            "cliente_nome *", "cliente_telefone *", "cliente_email", "cliente_documento", "cliente_data_nascimento", 
            "cliente_cep", "cliente_logradouro", "cliente_numero", "cliente_bairro", "cliente_cidade", "cliente_estado",
            "pet_nome", "pet_especie", "pet_raca", "pet_genero", "pet_porte", "pet_castrado", "pet_data_nascimento", "pet_observacoes"
        ]
        ws.append(headers)
        
        # Style headers (Client is light blue 1976D2, Pet is teal 00796B)
        font_style = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        client_fill = PatternFill(start_color="1976D2", end_color="1976D2", fill_type="solid")
        pet_fill = PatternFill(start_color="00796B", end_color="00796B", fill_type="solid")
        
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        left_align = Alignment(horizontal="left", vertical="center")
        
        thin_border = Border(
            left=Side(style="thin", color="D3D3D3"),
            right=Side(style="thin", color="D3D3D3"),
            top=Side(style="thin", color="D3D3D3"),
            bottom=Side(style="thin", color="D3D3D3")
        )
        
        ws.row_dimensions[1].height = 28
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = font_style
            cell.alignment = center_align
            cell.border = thin_border
            # Apply color based on group
            if col_idx <= 11:
                cell.fill = client_fill
            else:
                cell.fill = pet_fill
                
        # Add examples
        examples = [
            [
                "João Silva", "(11) 99999-8888", "joao@email.com", "123.456.789-00", "15/08/1985", 
                "01311-200", "Avenida Paulista", "1000", "Bela Vista", "São Paulo", "SP",
                "Rex", "Canino", "Golden Retriever", "Macho", "G", "Não", "01/05/2020", "Alérgico a medicamentos"
            ],
            [
                "João Silva", "(11) 99999-8888", "joao@email.com", "123.456.789-00", "15/08/1985", 
                "01311-200", "Avenida Paulista", "1000", "Bela Vista", "São Paulo", "SP",
                "Mia", "Felino", "Siamês", "Fêmea", "P", "Sim", "10/10/2022", "Muito dócil e assustada"
            ],
            [
                "Maria Souza", "(11) 88888-7777", "maria@email.com", "987.654.321-11", "20/10/1990", 
                "04533-010", "Rua Joaquim Floriano", "500", "Itaim Bibi", "São Paulo", "SP",
                "Fred", "Exótico", "Jabuti", "Macho", "PP", "Não", "01/01/2018", "Vive em terrário"
            ]
        ]
        
        for ex in examples:
            ws.append(ex)
            
        # Format rows up to 1000 (pre-styles cells so they format cleanly when typed)
        for r_idx in range(2, 1001):
            ws.row_dimensions[r_idx].height = 20
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=r_idx, column=col_idx)
                cell.font = Font(name="Segoe UI", size=10)
                cell.border = thin_border
                
                # Alignment
                if col_idx in [1, 3, 7, 9, 10, 12, 14, 19]:
                    cell.alignment = left_align
                else:
                    cell.alignment = center_align
                    
                # Format E (5) and R (18) as custom date mask
                if col_idx in [5, 18]:
                    cell.number_format = '00\\/00\\/0000'
                # Format B (2) as custom Phone mask
                elif col_idx == 2:
                    cell.number_format = '\\(00\\)\\ 00000\\-0000'
                # Format D (4) as custom CPF/CNPJ conditional mask
                elif col_idx == 4:
                    cell.number_format = '[>99999999999]00\\.000\\.000\\/0000\\-00;000\\.000\\.000\\-00'
                # Format F (6) as custom CEP mask
                elif col_idx == 6:
                    cell.number_format = '00000\\-000'
                    
        # Add validation rules
        # 1. Species (Column M - col 13)
        dv_species = DataValidation(type="list", formula1='"Canino,Felino,Exótico"', allow_blank=True)
        dv_species.error = 'Escolha uma espécie da lista (Canino, Felino ou Exótico)'
        dv_species.errorTitle = 'Espécie Inválida'
        dv_species.prompt = 'Selecione a espécie (Canino, Felino ou Exótico)'
        dv_species.promptTitle = 'Espécie'
        ws.add_data_validation(dv_species)
        dv_species.add("M2:M1000")
        
        # 2. Gender (Column O - col 15)
        dv_gender = DataValidation(type="list", formula1='"Macho,Fêmea,Desconhecido"', allow_blank=True)
        dv_gender.error = 'Escolha um gênero da lista'
        dv_gender.errorTitle = 'Gênero Inválido'
        dv_gender.prompt = 'Selecione o gênero'
        dv_gender.promptTitle = 'Gênero'
        ws.add_data_validation(dv_gender)
        dv_gender.add("O2:O1000")
        
        # 3. Size (Column P - col 16)
        dv_size = DataValidation(type="list", formula1='"PP,P,M,G,GG"', allow_blank=True)
        dv_size.error = 'Escolha um porte da lista'
        dv_size.errorTitle = 'Porte Inválido'
        dv_size.prompt = 'Selecione o porte'
        dv_size.promptTitle = 'Porte'
        ws.add_data_validation(dv_size)
        dv_size.add("P2:P1000")
        
        # 4. Neutered (Column Q - col 17)
        dv_neutered = DataValidation(type="list", formula1='"Sim,Não"', allow_blank=True)
        dv_neutered.error = 'Escolha Sim ou Não'
        dv_neutered.errorTitle = 'Opção Inválida'
        dv_neutered.prompt = 'O animal é castrado?'
        dv_neutered.promptTitle = 'Castrado'
        ws.add_data_validation(dv_neutered)
        dv_neutered.add("Q2:Q1000")
        
        # Column Widths
        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 13)
            
        ws.views.sheetView[0].showGridLines = True
        
        out = BytesIO()
        wb.save(out)
        return out.getvalue()

    async def import_clients_from_excel(self, db: Session, tenant_id: int, file_content: bytes):
        import openpyxl
        from app.modules.clients.models import Client
        
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
            
        raw_headers = rows[0]
        headers = []
        for h in raw_headers:
            if h is None:
                headers.append("")
            else:
                headers.append(str(h).strip().lower().replace("*", "").strip())
                
        required_cols = ["cliente_nome", "cliente_telefone"]
        missing_cols = [col for col in required_cols if col not in headers]
        if missing_cols:
            return {
                "imported": 0,
                "errors": [f"Colunas obrigatórias ausentes na planilha: {', '.join(missing_cols)}"]
            }
            
        imported_count = 0
        errors = []
        
        # Helpers
        def clean_str(val):
            if val is None or str(val).strip() == "":
                return None
            # Handle possible float values represented as string (like SKU/NCM/CEP)
            val_str = str(val).strip()
            if isinstance(val, float) and val.is_integer():
                return str(int(val))
            return val_str
            
        def clean_num(val):
            if val is None or str(val).strip() == "":
                return None
            return "".join(filter(str.isdigit, str(val)))
            
        def parse_date(val):
            if val is None or str(val).strip() == "":
                return None
            if hasattr(val, "date"):
                return val.date()
            if isinstance(val, date):
                return val
            try:
                # If Excel parses it as a float or int (e.g. 2071993.0)
                if isinstance(val, (int, float)):
                    cleaned = str(int(val))
                else:
                    cleaned = str(val).strip().replace("/", "").replace("-", "")
                    if "." in cleaned:
                        cleaned = cleaned.split(".")[0]

                # Pad leading zero if length is 7 (e.g. 2071993 -> 02071993)
                if len(cleaned) == 7 and cleaned.isdigit():
                    cleaned = "0" + cleaned
                
                if len(cleaned) == 8 and cleaned.isdigit():
                    # Format DDMMYYYY
                    return date(int(cleaned[4:8]), int(cleaned[2:4]), int(cleaned[0:2]))
                
                # Check original string if parsing above didn't match or failed
                cleaned_orig = str(val).strip()
                if "/" in cleaned_orig:
                    parts = cleaned_orig.split("/")
                    if len(parts) == 3:
                        return date(int(parts[2]), int(parts[1]), int(parts[0]))
                elif "-" in cleaned_orig:
                    parts = cleaned_orig.split("-")
                    if len(parts) == 3:
                        if len(parts[0]) == 4: # YYYY-MM-DD
                            return date(int(parts[0]), int(parts[1]), int(parts[2]))
                        else: # DD-MM-YYYY
                            return date(int(parts[2]), int(parts[1]), int(parts[0]))
            except Exception:
                pass
            return None

        def parse_species(val):
            if not val:
                return None
            cleaned = str(val).strip().lower()
            if "canino" in cleaned or "cão" in cleaned or "cao" in cleaned or "cachorro" in cleaned:
                return "Canino"
            if "felino" in cleaned or "gato" in cleaned:
                return "Felino"
            if "exotico" in cleaned or "exótico" in cleaned or "exoticos" in cleaned:
                return "Exoticos"
            return val


        def parse_gender(val):
            if not val:
                return "unknown"
            cleaned = str(val).strip().lower()
            if "macho" in cleaned:
                return "male"
            if "fêmea" in cleaned or "femea" in cleaned:
                return "female"
            return "unknown"

        def parse_neutered(val):
            if not val:
                return None
            cleaned = str(val).strip().lower()
            if "sim" in cleaned:
                return True
            if "não" in cleaned or "nao" in cleaned:
                return False
            return None

        # Local cache for client mapping to optimize and handle file-level repetition
        # key: (normalized_name, normalized_phone) or document
        client_cache = {}

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
                    
                # 1. Client Validation
                name = clean_str(row.get("cliente_nome"))
                phone = clean_str(row.get("cliente_telefone"))
                
                if not name:
                    raise ValueError("Nome do cliente é obrigatório")
                if not phone:
                    raise ValueError("Telefone do cliente é obrigatório")
                    
                email = clean_str(row.get("cliente_email"))
                
                # Pad document if Excel cut leading zero
                document = clean_num(row.get("cliente_documento"))
                if document:
                    if len(document) == 10:
                        document = "0" + document
                    elif len(document) == 13:
                        document = "0" + document
                        
                # Determine document_type
                document_type = None
                if document:
                    if len(document) == 11:
                        document_type = "CPF"
                    elif len(document) == 14:
                        document_type = "CNPJ"
                        
                birth_date = parse_date(row.get("cliente_data_nascimento"))
                
                # Pad CEP if Excel cut leading zero
                cep = clean_num(row.get("cliente_cep"))
                if cep and len(cep) == 7:
                    cep = "0" + cep
                    
                street = clean_str(row.get("cliente_logradouro"))
                number = clean_str(row.get("cliente_numero"))
                neighborhood = clean_str(row.get("cliente_bairro"))
                city = clean_str(row.get("cliente_cidade"))
                state = clean_str(row.get("cliente_estado"))
                
                # Check cache first, then DB
                client = None
                norm_name = name.lower().strip()
                norm_phone = "".join(filter(str.isdigit, phone))
                
                if document and document in client_cache:
                    client = client_cache[document]
                elif (norm_name, norm_phone) in client_cache:
                    client = client_cache[(norm_name, norm_phone)]
                    
                if not client:
                    # Query database
                    if document:
                        client = db.query(Client).filter(Client.tenant_id == tenant_id, Client.document == document).first()
                    if not client:
                        client = db.query(Client).filter(
                            Client.tenant_id == tenant_id, 
                            Client.name == name,
                            Client.phone == phone
                        ).first()
                        
                # Create client if doesn't exist
                if not client:
                    client_data = ClientCreate(
                        name=name,
                        phone=phone,
                        email=email,
                        document=document,
                        document_type=document_type,
                        birth_date=birth_date,
                        cep=cep,
                        street=street,
                        number=number,
                        neighborhood=neighborhood,
                        city=city,
                        state=state
                    )
                    client = self.repository.create(db, tenant_id, client_data)
                    
                # Cache client
                if document:
                    client_cache[document] = client
                client_cache[(norm_name, norm_phone)] = client
                
                # 2. Pet Validation & Creation
                pet_name = clean_str(row.get("pet_nome"))
                if pet_name:
                    pet_species_raw = clean_str(row.get("pet_especie"))
                    if not pet_species_raw:
                        raise ValueError("Espécie do pet é obrigatória quando o nome do pet é informado")
                    
                    pet_species = parse_species(pet_species_raw)
                    pet_breed = clean_str(row.get("pet_raca"))
                    pet_gender = parse_gender(clean_str(row.get("pet_genero")))
                    pet_size = clean_str(row.get("pet_porte"))
                    pet_neutered = parse_neutered(clean_str(row.get("pet_castrado")))
                    pet_birth = parse_date(row.get("pet_data_nascimento"))
                    pet_notes = clean_str(row.get("pet_observacoes"))
                    
                    from app.modules.pets.models import Pet
                    pet_in_db = db.query(Pet).filter(
                        Pet.tenant_id == tenant_id,
                        Pet.client_id == client.id,
                        Pet.name == pet_name,
                        Pet.species == pet_species
                    ).first()
                    
                    if not pet_in_db:
                        pet_data = PetCreate(
                            client_id=client.id,
                            name=pet_name,
                            species=pet_species,
                            breed=pet_breed,
                            gender=pet_gender,
                            size=pet_size,
                            is_neutered=pet_neutered,
                            birth_date=pet_birth,
                            notes=pet_notes
                        )
                        self.pet_repository.create(db, tenant_id, pet_data)
                        
                imported_count += 1
            except Exception as e:
                errors.append(f"Linha {row_idx}: {str(e)}")
                
        return {"imported": imported_count, "errors": errors}


