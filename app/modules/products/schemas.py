from datetime import datetime
from pydantic import BaseModel, ConfigDict, computed_field, model_validator
from typing import Optional, List, Any


class ProductPhotoResponse(BaseModel):
    id: int
    product_id: int
    photo_url: str
    is_primary: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductBase(BaseModel):
    name: str
    sku: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: float
    cost: Optional[float] = None
    quantity: int = 0
    min_stock: int = 0
    
    barcode: Optional[str] = None
    ncm: Optional[str] = None
    cest: Optional[str] = None
    cfop: Optional[str] = None
    csosn: Optional[str] = None
    cst_pis: Optional[str] = None
    cst_cofins: Optional[str] = None
    supplier_id: Optional[int] = None
    
    is_active: bool = True
    is_internal_use: bool = False
    unit: Optional[str] = "UN"

    @model_validator(mode="before")
    @classmethod
    def normalize_price_and_cost(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Se o cliente enviar price_cents em vez de price
            if "price_cents" in data and data["price_cents"] is not None and "price" not in data:
                data["price"] = round(float(data["price_cents"]) / 100.0, 2)
            # Se o cliente enviar cost_cents em vez de cost
            if "cost_cents" in data and data["cost_cents"] is not None and "cost" not in data:
                data["cost"] = round(float(data["cost_cents"]) / 100.0, 2)
        return data


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    cost: Optional[float] = None
    quantity: Optional[int] = None
    min_stock: Optional[int] = None
    
    barcode: Optional[str] = None
    ncm: Optional[str] = None
    cest: Optional[str] = None
    cfop: Optional[str] = None
    csosn: Optional[str] = None
    cst_pis: Optional[str] = None
    cst_cofins: Optional[str] = None
    supplier_id: Optional[int] = None
    
    is_active: Optional[bool] = None
    is_internal_use: Optional[bool] = None
    unit: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_price_and_cost(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "price_cents" in data and data["price_cents"] is not None and "price" not in data:
                data["price"] = round(float(data["price_cents"]) / 100.0, 2)
            if "cost_cents" in data and data["cost_cents"] is not None and "cost" not in data:
                data["cost"] = round(float(data["cost_cents"]) / 100.0, 2)
        return data


class ProductResponse(ProductBase):
    id: int
    photos: List[ProductPhotoResponse] = []

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def price_cents(self) -> int:
        return int(round(float(self.price) * 100)) if self.price is not None else 0

    @computed_field
    @property
    def cost_cents(self) -> Optional[int]:
        return int(round(float(self.cost) * 100)) if self.cost is not None else None
