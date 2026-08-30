from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

database_url = make_url(settings.database_url)
if database_url.drivername.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif database_url.drivername.endswith("psycopg") and database_url.port == 6543:
    # Supabase's transaction pooler can assign a different PostgreSQL backend to
    # each transaction, so driver-side prepared statements cannot be reused.
    connect_args = {"prepare_threshold": None}
else:
    connect_args = {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
class Base(DeclarativeBase): pass

def db_session():
    db = SessionLocal()
    try: yield db
    finally: db.close()
