import os
from typing import List, Union
from pydantic_settings import BaseSettings
from pydantic import field_validator
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # Database
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "freakfits_db")
    DB_SSL_CA: str = os.getenv("DB_SSL_CA", "")

    # Security
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "freakfits_super_secret_jwt_key_2026_change_in_production")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

    # SMTP / Email Configuration
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "FreakFits Matchday")

    # Server
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    CORS_ORIGINS: Union[str, List[str]] = ["*"]
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:8000")

    # Razorpay Payment Gateway
    RAZORPAY_KEY_ID: str = os.getenv("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET: str = os.getenv("RAZORPAY_KEY_SECRET", "")

    # Cloudinary Config
    CLOUDINARY_CLOUD_NAME: str = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY: str = os.getenv("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET: str = os.getenv("CLOUDINARY_API_SECRET", "")
    CLOUDINARY_FOLDER: str = os.getenv("CLOUDINARY_FOLDER", "freakfits")

    @property
    def database_url(self) -> str:
        import urllib.parse
        encoded_user = urllib.parse.quote_plus(self.DB_USER)
        
        base_url = ""
        if self.DB_PASSWORD:
            encoded_password = urllib.parse.quote_plus(self.DB_PASSWORD)
            base_url = f"mysql+mysqlconnector://{encoded_user}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        else:
            base_url = f"mysql+mysqlconnector://{encoded_user}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
            
        return base_url

    class Config:
        case_sensitive = True

settings = Settings()
