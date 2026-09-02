"""Engine, session factory, declarative Base, and startup schema setup.

Base is defined here but create_all() is deliberately NOT called at import
time - SQLAlchemy only creates tables for model classes that have already
been imported (registered on Base.metadata) by the time create_all() runs.
app/main.py imports every model module first, then calls init_db() once,
so import order never silently determines which tables get created.
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from . import config

engine = create_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_startup_migrations():
    """Best-effort ALTER TABLE for pre-existing Postgres databases.

    Base.metadata.create_all() only creates missing tables — it never adds
    columns/constraints to a table that already exists, so new user profile
    fields and the watchlist->user foreign key need to be patched in by hand.
    """
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_preference VARCHAR",
        """
        DO $$ BEGIN
            ALTER TABLE watchlists ADD CONSTRAINT fk_watchlists_user
                FOREIGN KEY (user_id) REFERENCES users(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,
        # group_id is new - Base.metadata.create_all() never alters an existing
        # table, so the column and its FK need the same manual treatment. Safe
        # on live data: a nullable column addition is metadata-only on Postgres
        # 11+, and FK constraints never validate against NULLs, so every
        # pre-existing alert row just gets group_id = NULL (shows up under "All").
        "ALTER TABLE watchlists ADD COLUMN IF NOT EXISTS group_id INTEGER",
        """
        DO $$ BEGIN
            ALTER TABLE watchlists ADD CONSTRAINT fk_watchlists_group
                FOREIGN KEY (group_id) REFERENCES stock_groups(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,
    ]
    # Each statement runs in its own transaction so one failure (e.g. a
    # pre-existing FK violation from orphaned rows) can't roll back the
    # others, such as the plain column additions.
    for statement in statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(statement))
        except Exception as exc:
            print(f"Startup migration statement skipped/failed: {exc}")


def init_db():
    """Creates every table registered on Base.metadata (and the news_pipeline
    package's own NewsBase), then runs the ALTER TABLE patches above. Call
    once at app startup, after every model module has been imported."""
    from news_pipeline.models import NewsBase

    Base.metadata.create_all(bind=engine)
    NewsBase.metadata.create_all(bind=engine)
    run_startup_migrations()
