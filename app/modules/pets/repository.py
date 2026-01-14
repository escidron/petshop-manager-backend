from app.modules.pets.models import Pet

class PetRepository:
    def get_pet(self, pet_id: int) -> Pet:
        # mock fixo por enquanto
        return Pet(
            id=pet_id,
            name="Bobby",
            species="dog",
        )
