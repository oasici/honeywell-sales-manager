"""Restore drill script safety-guard tests.

The drill script (``backend/scripts/restore_drill.sh``) drops and recreates
the public schema of STAGING_DATABASE_URL. If a misconfiguration or copy-paste
error ever points it at prod, the entire database is gone — no recovery
beyond the backup we're testing. These tests lock in the early-exit guards
that would catch such a mistake before any destructive command runs.

We don't need a real Postgres for these — the guards are in the first
~30 lines of the script and abort before anything is invoked.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "backend" / "scripts" / "restore_drill.sh"


def _run(env: dict) -> subprocess.CompletedProcess:
    """Invoke the drill script in a clean env with only the keys we want."""
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_script_exists_and_is_executable():
    assert SCRIPT.exists(), f"missing {SCRIPT}"
    assert SCRIPT.stat().st_mode & 0o100, "script is not executable (chmod +x)"


def test_aborts_when_prod_url_is_missing():
    """Without PROD_DB_BACKUP_URL the script must refuse to run."""
    result = _run({"STAGING_DATABASE_URL": "postgresql://staging.example.com/db"})
    assert result.returncode != 0
    assert "PROD_DB_BACKUP_URL" in result.stderr


def test_aborts_when_staging_url_is_missing():
    """Without STAGING_DATABASE_URL the script must refuse to run."""
    result = _run({"PROD_DB_BACKUP_URL": "postgresql://prod.example.com/db"})
    assert result.returncode != 0
    assert "STAGING_DATABASE_URL" in result.stderr


def test_aborts_when_staging_equals_prod():
    """Same URL on both sides would destroy prod — must fatal-exit."""
    same = "postgresql://example.com/honeywell"
    result = _run({"PROD_DB_BACKUP_URL": same, "STAGING_DATABASE_URL": same})
    assert result.returncode == 1
    assert "would destroy prod" in result.stderr


def test_aborts_when_staging_url_contains_prod_substring():
    """Defense in depth — refuse staging URLs that look like production."""
    result = _run({
        "PROD_DB_BACKUP_URL": "postgresql://backups.example.com/honeywell",
        "STAGING_DATABASE_URL": "postgresql://prod-replica.example.com/honeywell",
    })
    assert result.returncode == 1
    assert "looks like a production URL" in result.stderr


def test_aborts_when_staging_url_contains_production_substring():
    result = _run({
        "PROD_DB_BACKUP_URL": "postgresql://backups.example.com/honeywell",
        "STAGING_DATABASE_URL": "postgresql://production.example.com/honeywell",
    })
    assert result.returncode == 1
    assert "looks like a production URL" in result.stderr


def test_substring_check_is_case_insensitive():
    """``PROD`` in a URL is just as dangerous as ``prod``."""
    result = _run({
        "PROD_DB_BACKUP_URL": "postgresql://backups.example.com/honeywell",
        "STAGING_DATABASE_URL": "postgresql://PROD-east.example.com/honeywell",
    })
    assert result.returncode == 1
    assert "looks like a production URL" in result.stderr
