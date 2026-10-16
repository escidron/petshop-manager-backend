from pydantic import BaseModel, field_validator, model_validator
from datetime import datetime
from typing import Any


# =========================
# BASE
# =========================

class ServiceBase(BaseModel):
    name: str
    description: str | None = None
    species: list[str] | None = None
    sizes: list[str] | None = None
    coat_types: list[str] | None = None
    price_cents: int
    duration_minutes: int | None = None
    is_active: bool = True

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "size" in data and ("sizes" not in data or not data["sizes"]):
                val = data.get("size")
                data["sizes"] = [val] if val else None
            if "coat_type" in data and ("coat_types" not in data or not data["coat_types"]):
                val = data.get("coat_type")
                data["coat_types"] = [val] if val else None
        return data

    @field_validator("species", mode="before")
    @classmethod
    def normalize_species(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        def to_title(s: str) -> str:
            lower = s.strip().lower()
            if lower in ("canino", "cachorro", "cão", "cao"):
                return "Canino"
            if lower in ("felino", "gato"):
                return "Felino"
            if lower in ("exotico", "exótico", "exoticos", "exóticos"):
                return "Exotico"
            return s.strip().capitalize()

        if isinstance(v, str):
            v = v.strip()
            return [to_title(v)] if v else None
        if isinstance(v, (list, tuple)):
            cleaned = [to_title(str(x)) for x in v if str(x).strip()]
            return cleaned if cleaned else None
        return v

    @field_validator("sizes", mode="before")
    @classmethod
    def normalize_sizes(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            return [v] if v else None
        if isinstance(v, (list, tuple)):
            cleaned = [str(x).strip() for x in v if str(x).strip()]
            return cleaned if cleaned else None
        return v

    @field_validator("coat_types", mode="before")
    @classmethod
    def normalize_coat_types(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            return [v] if v else None
        if isinstance(v, (list, tuple)):
            cleaned = [str(x).strip() for x in v if str(x).strip()]
            return cleaned if cleaned else None
        return v


# =========================
# CREATE
# =========================

class ServiceCreate(ServiceBase):
    pass


# =========================
# UPDATE
# =========================

class ServiceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    species: list[str] | None = None
    sizes: list[str] | None = None
    coat_types: list[str] | None = None
    price_cents: int | None = None
    duration_minutes: int | None = None
    is_active: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "size" in data and "sizes" not in data:
                val = data.get("size")
                data["sizes"] = [val] if val else None
            if "coat_type" in data and "coat_types" not in data:
                val = data.get("coat_type")
                data["coat_types"] = [val] if val else None
        return data

    @field_validator("species", mode="before")
    @classmethod
    def normalize_species(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        def to_title(s: str) -> str:
            lower = s.strip().lower()
            if lower in ("canino", "cachorro", "cão", "cao"):
                return "Canino"
            if lower in ("felino", "gato"):
                return "Felino"
            if lower in ("exotico", "exótico", "exoticos", "exóticos"):
                return "Exotico"
            return s.strip().capitalize()

        if isinstance(v, str):
            v = v.strip()
            return [to_title(v)] if v else None
        if isinstance(v, (list, tuple)):
            cleaned = [to_title(str(x)) for x in v if str(x).strip()]
            return cleaned if cleaned else None
        return v

    @field_validator("sizes", mode="before")
    @classmethod
    def normalize_sizes(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            return [v] if v else None
        if isinstance(v, (list, tuple)):
            cleaned = [str(x).strip() for x in v if str(x).strip()]
            return cleaned if cleaned else None
        return v

    @field_validator("coat_types", mode="before")
    @classmethod
    def normalize_coat_types(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            return [v] if v else None
        if isinstance(v, (list, tuple)):
            cleaned = [str(x).strip() for x in v if str(x).strip()]
            return cleaned if cleaned else None
        return v


# =========================
# RESPONSE
# =========================

class ServiceResponse(ServiceBase):
    id: int
    created_at: datetime
    # Legacy backward compat fields
    size: str | None = None
    coat_type: str | None = None

    class Config:
        from_attributes = True

    @model_validator(mode="after")
    def populate_legacy_fields(self):
        if self.sizes:
            self.size = ", ".join(self.sizes)
        if self.coat_types:
            self.coat_type = ", ".join(self.coat_types)
        return self
