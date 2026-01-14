from pydantic import BaseModel

class PetResponse(BaseModel):
    id: int
    name: str
    species: str
