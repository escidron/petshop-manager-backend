import io
import re
import openpyxl
from io import BytesIO
from typing import Dict, List, Any, Optional
from datetime import date, datetime


def normalize_phone(val: Any) -> Optional[str]:
    """
    Intelligently cleans and normalizes phone numbers.
    Handles +55, 5511999998888, (11) 99999-8888, 011999998888, 11999998888, etc.
    Returns format (XX) 9XXXX-XXXX or (XX) XXXX-XXXX.
    """
    if val is None or str(val).strip() == "":
        return None

    raw = str(val).strip()
    digits = "".join(filter(str.isdigit, raw))

    if not digits:
        return None

    # Strip country code 55 if present
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]

    # Strip leading zero if present (e.g., 011999998888)
    if digits.startswith("0") and len(digits) in (11, 12):
        digits = digits[1:]

    # Standardize length: 10 digits (landline) or 11 digits (mobile)
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    elif len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    
    # Fallback to digits
    return raw


def clean_str(val: Any) -> Optional[str]:
    if val is None or str(val).strip() == "":
        return None
    val_str = str(val).strip()
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return val_str


def normalize_porte(val: Any) -> Optional[str]:
    if not val:
        return None
    cleaned = str(val).strip().lower()
    if "mini" in cleaned or "pp" in cleaned or "micro" in cleaned:
        return "PP"
    elif "pequeno" in cleaned or " p " in f" {cleaned} " or cleaned == "p":
        return "P"
    elif "médio" in cleaned or "medio" in cleaned or " m " in f" {cleaned} " or cleaned == "m":
        return "M"
    elif "grande" in cleaned or " g " in f" {cleaned} " or cleaned == "g":
        return "G"
    elif "gigante" in cleaned or "gg" in cleaned or "extra" in cleaned:
        return "GG"
    return str(val).strip()[:5]



class MigrationService:
    def inspect_excel_headers(self, file_content: bytes) -> List[str]:
        """
        Reads row 1 headers of an uploaded Excel file.
        """
        wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        
        raw_headers = rows[0]
        headers = []
        for h in raw_headers:
            if h is not None and str(h).strip() != "":
                headers.append(str(h).strip())
        return headers

    def parse_excel_rows(self, file_content: bytes) -> List[Dict[str, Any]]:
        """
        Parses an Excel file into a list of row dicts keyed by header name.
        """
        wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows or len(rows) < 2:
            return []

        headers = [str(h).strip() if h is not None else "" for h in rows[0]]
        
        parsed = []
        for row_values in rows[1:]:
            row_dict = {}
            has_val = False
            for h, val in zip(headers, row_values):
                if h:
                    row_dict[h] = val
                    if val is not None and str(val).strip() != "":
                        has_val = True
            if has_val:
                parsed.append(row_dict)
        return parsed

    def map_single_file(
        self,
        file_content: bytes,
        column_mapping: Dict[str, str],  # target_field -> source_header
        default_values: Dict[str, str] = None,  # target_field -> default_str
    ) -> List[Dict[str, Any]]:
        """
        Transforms a single competitor Excel file into system-standard rows.
        """
        default_values = default_values or {}
        source_rows = self.parse_excel_rows(file_content)
        
        transformed = []
        for row in source_rows:
            item = {}
            for target_field, source_col in column_mapping.items():
                if source_col and source_col in row:
                    val = row[source_col]
                    if target_field == "cliente_telefone":
                        val = normalize_phone(val)
                    elif target_field == "pet_porte":
                        val = normalize_porte(val)
                    else:
                        val = clean_str(val)
                    item[target_field] = val

                else:
                    item[target_field] = default_values.get(target_field)
            
            # Apply defaults for empty mapped fields if default exists
            for k, default_val in default_values.items():
                if not item.get(k) and default_val:
                    item[k] = default_val

            if item.get("cliente_nome") or item.get("pet_nome"):
                transformed.append(item)

        return transformed

    def map_two_files(
        self,
        clients_file_content: bytes,
        pets_file_content: bytes,
        client_link_key: str,  # e.g., 'ID Cliente' in clients file
        pet_link_key: str,     # e.g., 'ID Dono' in pets file
        client_column_mapping: Dict[str, str],  # cliente_* target -> client file header
        pet_column_mapping: Dict[str, str],     # pet_* target -> pet file header
        default_values: Dict[str, str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Joins separate Clients and Pets Excel files on matching ID key into system-standard rows.
        """
        default_values = default_values or {}
        client_rows = self.parse_excel_rows(clients_file_content)
        pet_rows = self.parse_excel_rows(pets_file_content)

        # Index client rows by link key
        client_by_key = {}
        for cr in client_rows:
            raw_key = cr.get(client_link_key)
            if raw_key is not None and str(raw_key).strip() != "":
                client_by_key[str(raw_key).strip()] = cr

        transformed = []
        for pr in pet_rows:
            raw_link = pr.get(pet_link_key)
            link_str = str(raw_link).strip() if raw_link is not None else ""
            client_row = client_by_key.get(link_str, {})

            item = {}
            # Map client fields
            for target_field, source_col in client_column_mapping.items():
                if source_col and source_col in client_row:
                    val = client_row[source_col]
                    if target_field == "cliente_telefone":
                        val = normalize_phone(val)
                    else:
                        val = clean_str(val)
                    item[target_field] = val
                else:
                    item[target_field] = default_values.get(target_field)

            # Map pet fields
            for target_field, source_col in pet_column_mapping.items():
                if source_col and source_col in pr:
                    val = pr[source_col]
                    if target_field == "pet_porte":
                        val = normalize_porte(val)
                    else:
                        val = clean_str(val)
                    item[target_field] = val
                else:
                    item[target_field] = default_values.get(target_field)


            # Apply defaults
            for k, default_val in default_values.items():
                if not item.get(k) and default_val:
                    item[k] = default_val

            if item.get("cliente_nome") or item.get("pet_nome"):
                transformed.append(item)

        return transformed

    def generate_converted_excel(self, items: List[Dict[str, Any]]) -> bytes:
        """
        Generates an Excel workbook formatted in our system's standard template schema from mapped items.
        """
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Clientes e Pets"

        headers = [
            "cliente_nome *", "cliente_telefone *", "cliente_email", "cliente_documento",
            "cliente_data_nascimento", "cliente_cep", "cliente_logradouro", "cliente_numero",
            "cliente_complemento", "cliente_bairro", "cliente_cidade", "cliente_estado",
            "pet_nome *", "pet_especie *", "pet_raca", "pet_tipo_pelagem", "pet_cor_pelagem",
            "pet_genero", "pet_porte", "pet_castrado", "pet_data_nascimento",
            "pet_idade_aproximada", "pet_unidade_idade", "pet_observacoes"
        ]
        ws.append(headers)

        header_keys = [
            "cliente_nome", "cliente_telefone", "cliente_email", "cliente_documento",
            "cliente_data_nascimento", "cliente_cep", "cliente_logradouro", "cliente_numero",
            "cliente_complemento", "cliente_bairro", "cliente_cidade", "cliente_estado",
            "pet_nome", "pet_especie", "pet_raca", "pet_tipo_pelagem", "pet_cor_pelagem",
            "pet_genero", "pet_porte", "pet_castrado", "pet_data_nascimento",
            "pet_idade_aproximada", "pet_unidade_idade", "pet_observacoes"
        ]

        for item in items:
            row = [item.get(k, "") or "" for k in header_keys]
            ws.append(row)

        out = BytesIO()
        wb.save(out)
        return out.getvalue()
