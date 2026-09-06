"""Date/time awareness tool."""

from __future__ import annotations

from datetime import datetime, timezone

from google.adk.tools import FunctionTool


def get_current_datetime() -> str:
    """Return the current UTC date and time in ISO-8601 form.

    Use this whenever the answer depends on "today" — e.g. notice periods,
    limitation windows, renewal or expiry dates.
    """
    return datetime.now(timezone.utc).isoformat()


get_current_datetime_tool = FunctionTool(get_current_datetime)
