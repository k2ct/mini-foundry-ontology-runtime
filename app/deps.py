"""
FastAPI dependency injection helpers.
"""

from typing import Generator

from app.database import SessionLocal


def get_db() -> Generator:
    """
    Yield a database session per request, ensuring the session is closed
    after the request finishes (even on errors).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
