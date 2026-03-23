from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Sync Accounting Software"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True
    
    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/sync_accounting"
    
    # JWT
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30  # 30 days (increased for desktop app to prevent auto-logout)
    
    # CORS
    CORS_ORIGINS: list = ["http://localhost:3000", "http://localhost:5173"]
    
    # File Upload
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    
    # QuickBooks Online API (Phase 2 - Optional)
    QUICKBOOKS_CLIENT_ID: Optional[str] = None
    QUICKBOOKS_CLIENT_SECRET: Optional[str] = None
    QUICKBOOKS_REDIRECT_URI: Optional[str] = None
    QUICKBOOKS_ENVIRONMENT: str = "sandbox"  # sandbox or production
    
    # OCR Services (Optional)
    TESSERACT_CMD: Optional[str] = None  # Path to tesseract executable (if not in PATH)
    GOOGLE_VISION_API_KEY: Optional[str] = None  # Path to Google Cloud service account JSON key file
    GOOGLE_VISION_PROJECT_ID: Optional[str] = None  # Google Cloud project ID (alternative to API key)
    GOOGLE_CLOUD_API_KEY: Optional[str] = None  # Legacy - kept for backward compatibility
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: Optional[str] = None
    
    # AI Services (Optional)
    OPENAI_API_KEY: Optional[str] = None  # OpenAI API key for text-to-number conversion
    USE_OPENAI_FOR_PAYEE_FALLBACK: bool = True  # When no rule matches, use OpenAI to normalize payee (if key set)
    
    # QuickBooks Web Connector
    QBWC_USERNAME: str = "admin"  # Default username for QB Web Connector
    QBWC_PASSWORD: str = "admin"  # Default password for QB Web Connector (can be overridden via env)
    
    # Email Service (Optional)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

