from app.modules.pets.repository import PetRepository
from app.modules.pets.service import PetService


def get_pet_service() -> PetService:
    return PetService(PetRepository())