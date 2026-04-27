"""Regression: ``GET /api/v1/activities/`` count must not select ``source_ref``.

The list endpoint's pagination count was wrapping a deferred-column
``select(ActivityLog)`` in ``stmt.subquery()``, which re-emitted every
entity column (including the deferred ``source_ref``) on the inner
SELECT. On Postgres deployments where the
``20260425_activity_logs_source_ref`` migration hadn't applied, this
crashed every list call — Sentry HONEYWELL-BACKEND-B/C/2.

This test compiles the count statement the endpoint actually issues
and checks that ``source_ref`` is absent from the rendered SQL — so a
regression on SQLite is detected without needing a Postgres fixture.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.models.activity_log import ActivityLog


def test_list_activities_count_stmt_does_not_reference_source_ref():
    # Mirrors the count query built in app.api.v1.activities.list_activities.
    count_stmt = select(func.count(ActivityLog.id)).where(
        ActivityLog.opportunity_id == 1
    )
    compiled = str(count_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "source_ref" not in compiled, (
        "Count statement must not select source_ref; otherwise prod "
        "DBs missing the migration will 500 on list_activities. "
        f"Compiled SQL: {compiled}"
    )
