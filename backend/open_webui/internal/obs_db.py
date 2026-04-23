import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base

from open_webui.env import DATABASE_URL, OBS_DATABASE_URL, DATABASE_ENABLE_SQLITE_WAL

log = logging.getLogger(__name__)


def sanitize_database_url(url: str) -> str:
    """Konsol loglari icin sifreyi maskele (postgresql://u:pw@h -> postgresql://***@h)."""
    if not url:
        return "(empty)"
    if "@" not in url or "://" not in url:
        return url
    try:
        scheme, rest = url.split("://", 1)
        _creds, hostpart = rest.rsplit("@", 1)
        return f"{scheme}://***@{hostpart}"
    except ValueError:
        return url[:120] + ("..." if len(url) > 120 else "")


def _create_obs_engine():
    """
    Tek PostgreSQL önerisi: OBS_DATABASE_URL bos birakilir veya DATABASE_URL ile ayni yazilir —
    obs_* tablolari ana uygulama ile AYNI engine / connection pool üzerinden okunur.
    """
    obs = (OBS_DATABASE_URL or "").strip()
    primary = (DATABASE_URL or "").strip()
    if not obs or obs == primary:
        from open_webui.internal.db import engine as primary_engine

        if not obs:
            log.info(
                "OBS: OBS_DATABASE_URL bos — obs_* verisi DATABASE_URL (primary) ile tek DB."
            )
        else:
            log.info(
                "OBS: OBS_DATABASE_URL DATABASE_URL ile ayni — tek havuz (primary engine)."
            )
        return primary_engine

    url = obs
    if "sqlite" in url.lower():
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
OBS_USES_PRIMARY_DATABASE = (not bool((OBS_DATABASE_URL or "").strip())) or (
    (OBS_DATABASE_URL or "").strip() == (DATABASE_URL or "").strip()
)
OBS_ENGINE_URL_SAFE = sanitize_database_url(str(obs_engine.url))

log.info(
    "[OBS-DB] tek_db=%s | motor_url=%s | OBS_DATABASE_URL=%s",
    OBS_USES_PRIMARY_DATABASE,
    OBS_ENGINE_URL_SAFE,
    "bos veya DATABASE_URL ile ayni" if OBS_USES_PRIMARY_DATABASE else "ayri sunucu",
)
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
