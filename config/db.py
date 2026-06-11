from __future__ import annotations

import os
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker, Session
from models import Base

from dotenv import load_dotenv

load_dotenv()

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Database connection string
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/tccc_analytics"
)

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("DB_ECHO", "False").lower() in ("1", "true", "yes"),
    pool_pre_ping=True,
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db() -> Session:
    """Generate database session for dependency injection"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize database by creating all tables from models.
    Called on application startup.
    """
    try:
        # Create all tables that don't exist
        Base.metadata.create_all(bind=engine)
        # Quick verification: attempt a lightweight connection
        with engine.connect() as conn:
            version = conn.execute(text("select version()")).scalar()
    except Exception as e:
        # Make exceptions loud so we see failures during startup
        print(f"[DB] ✗ Error initializing database: {e}", flush=True)
        raise