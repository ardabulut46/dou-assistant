import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base

from open_webui.env import OBS_DATABASE_URL, DATABASE_ENABLE_SQLITE_WAL

log = logging.getLogger(__name__)


def _create_obs_engine():
    # Fallback to primary DB if OBS_DATABASE_URL not set
    url = OBS_DATABASE_URL.strip()
    if not url:
        from open_webui.internal.db import engine as primary_engine

        log.info("OBS_DATABASE_URL not set; using primary database for OBS data")
        return primary_engine

    if "sqlite" in url:
        engine = create_engine(url, connect_args={"check_same_thread": False})

        def on_connect(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            if DATABASE_ENABLE_SQLITE_WAL:
                cursor.execute("PRAGMA journal_mode=WAL")
            else:
                cursor.execute("PRAGMA journal_mode=DELETE")
            cursor.close()

        event.listen(engine, "connect", on_connect)
        return engine

    return create_engine(url, pool_pre_ping=True)


obs_engine = _create_obs_engine()
ObsSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=obs_engine, expire_on_commit=False
)
ObsScopedSession = scoped_session(ObsSessionLocal)
ObsBase = declarative_base()


def get_obs_session():
    db = ObsSessionLocal()
    try:
        yield db
    finally:
        db.close()


get_obs_db = contextmanager(get_obs_session)


@contextmanager
def get_obs_db_context(db: "Session" = None):
    if isinstance(db, Session):
        yield db
    else:
        with get_obs_db() as session:
            yield session
