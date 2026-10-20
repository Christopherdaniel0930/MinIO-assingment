from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str = "documents"
    minio_secure: bool = False

    database_url: str = "sqlite:///./documents.db"
    max_file_size_mb: int = 10
    presigned_url_expiry_seconds: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()