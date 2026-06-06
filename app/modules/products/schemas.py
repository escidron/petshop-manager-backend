from pydantic import BaseModel, ConfigDict
from typing import Optional


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
    unit: Optional[str] = "UN"


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
    unit: Optional[str] = None


class ProductResponse(ProductBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
