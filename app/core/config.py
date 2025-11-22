from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Jarvis MVP"
    
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URL: str
    
    REDIS_HOST: str
    REDIS_PORT: int

    TELNYX_API_KEY: str
    TELNYX_PUBLIC_KEY: str | None = None
    TELNYX_PHONE_NUMBER: str | None = None
    
    OPENAI_API_KEY: str | None = None

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
