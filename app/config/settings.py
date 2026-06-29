from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    APP_NAME: str = "Pet Controle"
    # Security
    JWT_SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Cookies
    COOKIE_ACCESS_NAME: str = "access_token"
    COOKIE_REFRESH_NAME: str = "refresh_token"
    CEP_BASE_URL: str

    # Pagar.me
    PAGARME_SECRET_KEY: str = ""
    PAGARME_PUBLIC_KEY: str = ""
    PAGARME_WEBHOOK_SECRET: str = ""

    # Email (Resend)
    RESEND_KEY: str = ""
    DEFAULT_FROM_EMAIL: str = "onboarding@resend.dev"
    ADMIN_EMAIL: str = ""

    # CORS — comma-separated list of allowed origins
    # Ex: "https://meuapp.vercel.app,https://www.meuapp.com"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Set to "production" to disable SQL echo
    ENVIRONMENT: str = "development"

    # Google Cloud Storage
    GCP_PROJECT_ID: str = ""
    GCP_CLIENT_EMAIL: str = ""
    GCP_PRIVATE_KEY: str = ""
    GCS_BUCKET_NAME: str = ""

    # WhatsApp Config
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_sandbox_mode: bool = True
    whatsapp_sandbox_number: str = ""
    whatsapp_template_appointment: str = ""
    whatsapp_webhook_verify_token: str = ""
    app_access_token: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

