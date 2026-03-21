from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Cookies
    COOKIE_ACCESS_NAME: str = "access_token"
    COOKIE_REFRESH_NAME: str = "refresh_token"
    CEP_BASE_URL: str

    # CORS — comma-separated list of allowed origins
    # Ex: "https://meuapp.vercel.app,https://www.meuapp.com"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Set to "production" to disable SQL echo
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"


settings = Settings()
