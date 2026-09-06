"""Relabel blank DD reports that were stored as 'ready'

Revision ID: 014
Revises: 013
Create Date: 2026-08-14

run_dd used to set status='ready' unconditionally, even when the screening
adapter had returned an audit carrying an `_error`. Those runs produced no
findings and a 0.0 score, so a vendor that failed screening was indistinguishable
in the UI from a vendor that came back clean — and opening one showed an empty
report with the raw internal code ("unparseable_model_response") printed at the
user.

run_dd now marks such runs 'failed' at write time. This backfills the rows
written before that fix so they render as failed screenings with a retry, in
every environment that ran the buggy code.
"""
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only rows the adapter itself flagged. A genuinely clean screening has no
    # _error key, so it is untouched regardless of its score.
    op.execute(
        """
        UPDATE dd_reports
        SET status = 'failed',
            error = COALESCE(
                NULLIF(error, ''),
                NULLIF(audit_data -> 'risk' ->> 'summary', ''),
                'Screening did not return a usable audit. Re-run the screening.'
            )
        WHERE status = 'ready'
          AND audit_data ? '_error'
          AND COALESCE(audit_data ->> '_error', '') <> ''
        """
    )

    # Runs interrupted mid-flight (server restart, killed worker) sit in
    # 'processing' forever and block the vendor from being re-screened.
    op.execute(
        """
        UPDATE dd_reports
        SET status = 'failed',
            error = COALESCE(NULLIF(error, ''),
                             'Screening did not complete — the run was interrupted.')
        WHERE status = 'processing'
          AND created_at < NOW() - INTERVAL '10 minutes'
        """
    )


def downgrade() -> None:
    # Restore only what this migration relabelled — identifiable by the _error
    # key. The interrupted 'processing' rows are not restored: they were never
    # a meaningful state to return to.
    op.execute(
        """
        UPDATE dd_reports
        SET status = 'ready'
        WHERE status = 'failed'
          AND audit_data ? '_error'
          AND COALESCE(audit_data ->> '_error', '') <> ''
        """
    )
