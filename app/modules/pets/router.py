from fastapi import APIRouter, Depends
from app.modules.pets.dependencies import get_pet_service
from app.modules.pets.service import PetService
from app.modules.pets.schemas import PetResponse

router = APIRouter(prefix="/pets", tags=["Pets"])

@router.get("/{pet_id}", response_model=PetResponse)
def get_pet(
    pet_id: int,
    service: PetService = Depends(get_pet_service),
):
    pet = service.get_pet(pet_id)
    return pet
