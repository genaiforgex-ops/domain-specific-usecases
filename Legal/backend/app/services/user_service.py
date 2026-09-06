"""Hard-delete a user and everything that references them.

Permanent deletion is tricky because ~20 tables carry a FK to ``users.id``. This
helper resolves those references generically from the database's own FK
metadata, so it stays correct as new tables are added:

  - **Nullable** attribution columns (e.g. ``audit_logs.user_id``,
    ``msa_trackers.assigned_to_id``) are set to NULL — the record is kept, just
    detached from the deleted user (preserves audit history).
  - **Non-nullable** ownership columns (e.g. ``chat_sessions.user_id``,
    ``notifications.user_id``) mean the row belongs to the user, so it is
    deleted.

All in one transaction (the caller commits). Postgres-specific (information_schema).
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("legalos.users")


def _user_fk_columns(db: Session) -> list[tuple[str, str, bool]]:
    """Return (table, column, nullable) for every FK pointing at users.id."""
    rows = db.execute(
        text(
            """
            SELECT tc.table_name,
                   kcu.column_name,
                   (SELECT c.is_nullable
                      FROM information_schema.columns c
                     WHERE c.table_name = tc.table_name
                       AND c.column_name = kcu.column_name) AS is_nullable
              FROM information_schema.table_constraints tc
              JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
              JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
             WHERE tc.constraint_type = 'FOREIGN KEY'
               AND ccu.table_name = 'users'
               AND ccu.column_name = 'id'
            """
        )
    ).fetchall()
    return [(r[0], r[1], (r[2] == "YES")) for r in rows]


def _incoming_fk_columns(db: Session, parent_table: str) -> list[tuple[str, str, bool]]:
    """Return (child_table, child_column, nullable) for FKs referencing parent_table."""
    rows = db.execute(
        text(
            """
            SELECT kcu.table_name,
                   kcu.column_name,
                   (SELECT c.is_nullable
                      FROM information_schema.columns c
                     WHERE c.table_name = kcu.table_name
                       AND c.column_name = kcu.column_name) AS is_nullable
              FROM information_schema.table_constraints tc
              JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
              JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
             WHERE tc.constraint_type = 'FOREIGN KEY'
               AND ccu.table_name = :parent_table
               AND kcu.table_name != :parent_table
            """
        ),
        {"parent_table": parent_table},
    ).fetchall()
    return [(r[0], r[1], (r[2] == "YES")) for r in rows]


def _detach_incoming_fks(
    db: Session, table: str, filter_column: str, user_id: int
) -> None:
    """Null out nullable FKs that point at rows we are about to delete."""
    for child_table, child_column, nullable in _incoming_fk_columns(db, table):
        if not nullable:
            continue
        db.execute(
            text(
                f"""
                UPDATE {child_table}
                   SET {child_column} = NULL
                 WHERE {child_column} IN (
                       SELECT id FROM {table} WHERE {filter_column} = :uid
                 )
                """
            ),
            {"uid": user_id},
        )


def hard_delete_user(db: Session, user_id: int) -> None:
    """Permanently remove a user and their references. Does not commit."""
    for table, column, nullable in _user_fk_columns(db):
        if nullable:
            db.execute(
                text(f"UPDATE {table} SET {column} = NULL WHERE {column} = :uid"),
                {"uid": user_id},
            )
        else:
            # Child rows may still reference records we own (e.g. msa_document_versions
            # → document_comparisons). Detach those first so DELETE does not violate FKs.
            _detach_incoming_fks(db, table, column, user_id)
            db.execute(
                text(f"DELETE FROM {table} WHERE {column} = :uid"),
                {"uid": user_id},
            )
    db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
    logger.info("Hard-deleted user id=%s and detached/removed its references", user_id)
