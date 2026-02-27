import httpx

from app.config.settings import settings

class AddressService:

    @staticmethod
    def _normalize_cep(cep: str) -> str:
        return cep.replace("-", "").replace(".", "").strip()

    @staticmethod
    async def fetch_by_cep(cep: str) -> dict | None:
        cep = AddressService._normalize_cep(cep)

        if len(cep) != 8 or not cep.isdigit():
            return None

        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{settings.CEP_BASE_URL}/{cep}/json/")
            data = response.json()

        if data.get("erro"):
            return None

        return {
            "cep": data.get("cep"),
            "street": data.get("logradouro"),
            "neighborhood": data.get("bairro"),
            "city": data.get("localidade"),
            "state": data.get("uf"),
        }
