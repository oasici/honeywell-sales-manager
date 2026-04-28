"""P0-1: Scheduler integration tests."""

import pytest

from app.tasks.scheduler import scheduler, start_scheduler, stop_scheduler


def test_start_scheduler_registers_all_jobs():
    """start_scheduler() must register all required background jobs."""
    if scheduler.running:
        scheduler.shutdown(wait=False)

    start_scheduler()

    try:
        job_ids = {job.id for job in scheduler.get_jobs()}
        assert "email_poll" in job_ids, "email_poll job not registered"
        assert "quote_expiry" in job_ids, "quote_expiry job not registered"
        assert "batch_email_process" in job_ids, "batch_email_process job not registered"
        assert "pipeline_snapshot" in job_ids, "pipeline_snapshot job not registered"
        assert "scheduled_reports" in job_ids, "scheduled_reports job not registered"
        assert "kvkk_anonymize" in job_ids, "kvkk_anonymize job not registered"
        assert "v4_feature_store" in job_ids, "v4_feature_store job not registered"
        assert "v4_sales_events_shadow" in job_ids, "v4_sales_events_shadow job not registered"
        assert "v4_sales_dna_nightly" in job_ids, "v4_sales_dna_nightly job not registered"
        assert "v4_deal_replay_nightly" in job_ids, "v4_deal_replay_nightly job not registered"
        assert "v5_intelligence_nightly" in job_ids, "v5_intelligence_nightly job not registered"
        assert "rag_incremental_backfill" in job_ids, "rag_incremental_backfill job not registered"
        assert len(job_ids) == 20, f"Expected 20 jobs, got {len(job_ids)}: {job_ids}"
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


def test_stop_scheduler_runs_without_error():
    """stop_scheduler() must complete without raising exceptions.

    Note: AsyncIOScheduler.shutdown() requires an event loop to fully
    transition state. In sync test context, we verify no exception is raised
    and that the function is safe to call. In production (async lifespan),
    shutdown works correctly.
    """
    if not scheduler.running:
        start_scheduler()

    # Must not raise
    stop_scheduler()


def test_start_scheduler_idempotent():
    """Calling start_scheduler() twice should not create duplicate jobs."""
    if scheduler.running:
        scheduler.shutdown(wait=False)

    start_scheduler()
    start_scheduler()  # second call — should replace, not duplicate

    try:
        job_ids = [job.id for job in scheduler.get_jobs()]
        assert len(job_ids) == 20, f"Duplicate jobs detected: {job_ids}"
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


def test_stop_scheduler_idempotent():
    """Calling stop_scheduler() when already stopped should not raise."""
    if scheduler.running:
        scheduler.shutdown(wait=False)

    # Should not raise
    stop_scheduler()
    stop_scheduler()
