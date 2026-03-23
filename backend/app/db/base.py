from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,  # Increased pool size
    max_overflow=20,  # Increased overflow
    pool_recycle=3600,  # Recycle connections after 1 hour
    echo=settings.DEBUG,
    # Explicit search_path so the app works when the DB user has an empty/custom default (e.g. on deploy).
    connect_args={"options": "-c search_path=public"},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

