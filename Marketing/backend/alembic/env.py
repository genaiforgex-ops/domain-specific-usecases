"""Alembic environment — wires migrations to the app's engine and metadata."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import settings
from app.database import Base
import app.models  # noqa: F401 — import for side effect: registers models on Base

config = context.config
# Apply alembic.ini's logging config, but DON'T disable already-configured
# loggers. The app runs `alembic upgrade head` inside the uvicorn process on
# startup; the default disable_existing_loggers=True would silence uvicorn's
# access logs and the app's own loggers (including email send logs) for the
# rest of the process's life.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
