from fastapi import APIRouter, HTTPException

from app.modules.address.schemas import AddressResponse
from app.modules.address.service import AddressService

router = APIRouter(
    prefix="/address",
    tags=["Address"]
)

@router.get("/{cep}", response_model=AddressResponse)
async def get_address_by_cep(cep: str):
    address = await AddressService.fetch_by_cep(cep)

    if not address:
        raise HTTPException(
            status_code=404,
            detail="CEP não encontrado"
        )
    
    return address
