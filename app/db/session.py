from sqlmodel import create_engine, Session
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, echo=settings.sqlalchemy_echo)


def get_session():
    """Get database session for dependency injection"""
    with Session(engine) as session:
        yield session
