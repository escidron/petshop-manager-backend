import os
from google.cloud import storage
from google.oauth2 import service_account
from app.config.settings import settings

class GCSService:
    def __init__(self):
        # Se as credenciais estiverem no .env (como no Vercel ou local com chaves explícitas)
        if settings.GCP_PRIVATE_KEY and settings.GCP_CLIENT_EMAIL:
            # Substitui quebras de linha escapadas que costumam vir em strings no .env
            private_key = settings.GCP_PRIVATE_KEY.replace("\\n", "\n")
            info = {
                "type": "service_account",
                "project_id": settings.GCP_PROJECT_ID,
                "private_key": private_key,
                "client_email": settings.GCP_CLIENT_EMAIL,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
            credentials = service_account.Credentials.from_service_account_info(info)
            self.client = storage.Client(project=settings.GCP_PROJECT_ID, credentials=credentials)
        else:
            # Em produção no Cloud Run, ou local com gcloud CLI (Application Default Credentials)
            self.client = storage.Client()

        self.bucket_name = settings.GCS_BUCKET_NAME
        self.bucket = self.client.bucket(self.bucket_name)

    def upload_file(self, file_content: bytes, destination_blob_name: str, content_type: str) -> str:
        """Faz o upload de um arquivo para o GCS e retorna a sua URL pública."""
        blob = self.bucket.blob(destination_blob_name)
        blob.upload_from_string(file_content, content_type=content_type)
        return blob.public_url

    def delete_file(self, destination_blob_name: str) -> None:
        """Deleta um arquivo do GCS se ele existir."""
        blob = self.bucket.blob(destination_blob_name)
        if blob.exists():
            blob.delete()
