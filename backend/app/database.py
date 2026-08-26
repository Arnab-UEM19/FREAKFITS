import logging

import mysql.connector
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from .config import settings

logger = logging.getLogger("uvicorn")

def create_database_if_not_exists():
    """Ensure the MySQL database exists before creating tables."""
    try:
        connect_args = {
            "host": settings.DB_HOST,
            "port": settings.DB_PORT,
            "user": settings.DB_USER,
            "password": settings.DB_PASSWORD,
            "charset": "utf8mb4"
        }
        if settings.DB_SSL_CA:
            connect_args["ssl_ca"] = settings.DB_SSL_CA
            connect_args["ssl_verify_cert"] = True
            connect_args["ssl_verify_identity"] = True
            
        conn = mysql.connector.connect(**connect_args)
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{settings.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Verified MySQL database `{settings.DB_NAME}`")
    except Exception as e:
        logger.warning(f"Note: Could not auto-create database `{settings.DB_NAME}` via root connection: {e}")

def get_engine():
    """Attempt MySQL connection; fallback to SQLite if MySQL is unavailable or unconfigured."""
    create_database_if_not_exists()
    mysql_url = settings.database_url
    try:
        engine_connect_args = {"connect_timeout": 3}
        if settings.DB_SSL_CA:
            engine_connect_args["ssl_ca"] = settings.DB_SSL_CA
            engine_connect_args["ssl_verify_cert"] = True
            engine_connect_args["ssl_verify_identity"] = True

        test_engine = create_engine(
            mysql_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=5,
            max_overflow=10,
            connect_args=engine_connect_args
        )
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info(f"Connected successfully to MySQL database `{settings.DB_NAME}` at {settings.DB_HOST}:{settings.DB_PORT}")
        return test_engine
    except Exception as e:
        logger.warning(
            f"MySQL connection probe failed ({e}).\n"
            f"--> Please set your MySQL password in `backend/.env` (e.g. DB_PASSWORD=your_password).\n"
            f"--> Using local SQLite `freakfits.db` for now so the backend runs seamlessly."
        )
        sqlite_engine = create_engine(
            "sqlite:///./freakfits.db",
            connect_args={"check_same_thread": False}
        )
        return sqlite_engine

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Request-scoped dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
