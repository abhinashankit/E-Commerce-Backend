from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY: str = "dev-secret-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ORDER_EXPIRY_MINUTES: int = 15

    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/ecommerce"
    REDIS_URL: str = "redis://localhost:6379/0"

    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    RATE_LIMIT_DEFAULT: int = 100
    RATE_LIMIT_ORDERS: int = 10
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    CACHE_TTL_SECONDS: int = 60

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "no-reply@example.com"
    SMS_API_URL: str = ""
    SMS_API_KEY: str = ""


settings = Settings()
