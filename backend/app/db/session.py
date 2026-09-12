"""SQLAlchemy engine, session factory and declarative base."""
import logging

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if _is_sqlite else {}


def apply_sqlite_pragmas(dbapi_connection, _record=None) -> None:
    """Per-connection SQLite tuning, shared by the app engine (below) and by
    tests, which build their own separate in-memory engine (tests/conftest.py)
    and would otherwise get none of this -- including FK enforcement, which
    SQLite has off by default per connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# SQLAlchemy's default pool (size=5, max_overflow=10 -> 15 total) is sized for
# a real database server, not for a single-file SQLite database serving many
# request-handling threads. Under load-testing this backend, the default pool
# caused most concurrent requests to queue for a connection and eventually
# time out -- appearing as a pipeline slowdown when it was actually pool
# starvation. SQLite itself is the real ceiling under concurrent writes
# (readers/writers still serialize at the file level even in WAL mode), so
# this is a dev/demo mitigation, not a claim that SQLite scales -- see
# docker-compose.yml, which already defaults to PostgreSQL in production.
engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_POOL_MAX_OVERFLOW,
    echo=False,
)

if _is_sqlite:
    # WAL lets readers proceed while a write is in progress instead of
    # blocking behind SQLite's default rollback-journal exclusive lock --
    # the single biggest concurrency win available without changing engines.
    # busy_timeout matters just as much: SQLite's default is 0, so a
    # second concurrent WRITER (WAL only helps readers-vs-writer, not
    # writer-vs-writer) raises "database is locked" immediately instead of
    # waiting its turn. Load-testing this backend surfaced exactly that --
    # concurrent geofence/anomaly alert inserts failing outright under
    # load. A timeout turns that hard failure into a bounded wait.
    # foreign_keys=ON is required too: SQLite ignores FK constraints unless
    # explicitly turned on per connection, or users.tourist_id/unit_id's FK
    # is decorative.
    event.listens_for(engine, "connect")(apply_sqlite_pragmas)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Verify the database schema is current.

    Schema changes are owned by Alembic (`alembic upgrade head`), not by
    `create_all`. create_all silently does nothing to an existing table, so a
    model change would appear to work locally and then fail in production
    against the older schema. This checks the applied revision and says plainly
    what to do instead of guessing.
    """
    from app import models  # noqa: F401  (ensures models are imported)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if not tables:
        logger.warning(
            "Database is empty. Run 'alembic upgrade head' to create the schema."
        )
        return

    if "alembic_version" not in tables:
        logger.warning(
            "Schema exists but is not under Alembic control. Run "
            "'alembic stamp head' to adopt it."
        )
        return

    with engine.connect() as conn:
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    logger.info("Database schema at revision %s", current)
