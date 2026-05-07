from fastapi import APIRouter, HTTPException, Request
from app.config.limiter import limiter

from app.modules.address.schemas import AddressResponse
from app.modules.address.service import AddressService

router = APIRouter(
    prefix="/address",
    tags=["Address"]
)

@router.get("/{cep}", response_model=AddressResponse)
@limiter.limit("15/minute")
async def get_address_by_cep(request: Request, cep: str):
    address = await AddressService.fetch_by_cep(cep)

    if not address:
        raise HTTPException(
            status_code=404,
            detail="CEP não encontrado"
        )
    
    return address
