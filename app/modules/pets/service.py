from app.modules.pets.repository import PetRepository
from app.modules.pets.models import Pet

class PetService:
    def __init__(self, repository: PetRepository):
        self.repository = repository

    def get_pet(self, pet_id: int) -> Pet:
        return self.repository.get_pet(pet_id)
