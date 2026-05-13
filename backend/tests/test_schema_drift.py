"""Round-5 R5-DB-8 — schema-drift pytest gate.

Pre-R5 the schema_check tool ran only as a CI shell step, so a developer
running ``pytest`` locally got a green build even when their PR
introduced model↔migration drift. The first signal of drift was a red
CI build, which is the wrong loop position. This test runs the same
check in pytest so the local feedback is immediate.

Two complementary tests:

1. ``test_no_schema_drift_against_test_db`` — introspects the live
   migrated test DB and compares to ``Base.metadata``. Skips when
   ``TEST_DATABASE_URL`` is unset (offline boxes / fast unit-only
   runs).

2. ``test_bootstrap_creates_every_model_table`` — pure file
   inspection. Greps the bootstrap migration for ``CREATE TABLE``
   statements and asserts every Mapped table is present. Catches the
   R5-DB-1 class of bug (model added, regenerator not re-run) before
   merge.

3. ``test_migration_chain_is_linear_with_single_head`` — backstop for
   accidental forks / orphans during round-5's two new migrations
   (20260505_pipeline_tenant + 20260505_breach_folder_tenant +
   20260505_drop_dup_indexes).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from app import models  # noqa: F401  — register all mappers
from app.core.database import Base


_VERSIONS_DIR = Path(__file__).resolve().parent.parent / "alembic" / "versions"
_BOOTSTRAP = _VERSIONS_DIR / "20260101_bootstrap_legacy.py"


@pytest.mark.schema
def test_bootstrap_creates_every_model_table() -> None:
    """R5-DB-1 — bootstrap snapshot must include every Mapped table.

    When a developer adds a new model, they must re-run
    ``backend/scripts/regenerate_bootstrap_migration.py`` so the
    bootstrap stays canonical. This test fails loudly when the
    snapshot drifts behind ``Base.metadata``.
    """
    if not _BOOTSTRAP.exists():
        pytest.skip("bootstrap migration not present in this checkout")

    src = _BOOTSTRAP.read_text()
    declared = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", src))
    expected = {t.name for t in Base.metadata.sorted_tables}
    missing = expected - declared
    assert not missing, (
        f"Bootstrap snapshot missing {len(missing)} model table(s): "
        f"{sorted(missing)}. Run "
        "backend/scripts/regenerate_bootstrap_migration.py."
    )


@pytest.mark.schema
def test_migration_chain_is_linear_with_single_head() -> None:
    """R5-DB-8 — every revision has at most one parent and one child."""
    revisions: dict[str, str | None] = {}
    for path in _VERSIONS_DIR.glob("*.py"):
        text = path.read_text()
        rm = re.search(r'^revision\s*=\s*"([^"]+)"', text, re.M)
        dm = re.search(r'^down_revision\s*=\s*("[^"]+"|None)', text, re.M)
        if not rm or not dm:
            continue
        d = None if dm.group(1) == "None" else dm.group(1).strip('"')
        revisions[rm.group(1)] = d

    bases = [r for r, d in revisions.items() if d is None]
    assert len(bases) == 1, f"Expected 1 base, got {bases}"

    referenced = {d for d in revisions.values() if d is not None}
    heads = set(revisions) - referenced
    assert len(heads) == 1, f"Expected 1 head, got {heads}"

    children: dict[str | None, list[str]] = {}
    for r, d in revisions.items():
        children.setdefault(d, []).append(r)
    forks = {p: c for p, c in children.items() if p is not None and len(c) > 1}
    assert not forks, f"Fork detected — multiple children share a parent: {forks}"

    orphans = {
        r: d for r, d in revisions.items() if d is not None and d not in revisions
    }
    assert not orphans, f"Orphan revision references: {orphans}"


@pytest.mark.schema
def test_no_schema_drift_against_test_db() -> None:
    """R5-DB-8 — live DB introspection must match Base.metadata.

    Skips when:
      * ``TEST_DATABASE_URL`` is unset (offline / unit-only run); or
      * the configured DB is SQLite (Round-14 R14-DB-1 — SQLite has no
        native timezone-aware type, so every ``Mapped[datetime]`` column
        backed by ``DateTime(timezone=True)`` reports a spurious
        ``TIMESTAMPTZ vs DATETIME`` mismatch. The drift gate is meant
        for Postgres; the SQLite false positive masked real drift
        signal and broke the gate's promise. Production uses Postgres
        exclusively, so SQLite-only test runs skip this assertion
        rather than producing 50+ noise lines).

    CI must set ``TEST_DATABASE_URL`` to a Postgres URL for the gate
    to actually fire.
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")

    if url.startswith("sqlite") or "sqlite" in url:
        pytest.skip(
            "Schema-drift gate requires Postgres — SQLite has no "
            "native timezone-aware DateTime, so TIMESTAMPTZ columns "
            "report spurious drift. See R14-DB-1."
        )

    # ``check_schema`` is async-only as of round-4 v1.9.6; run via the
    # CLI module to keep this test sync (pytest-asyncio is configured
    # but we don't want a per-event-loop dependency on this gate).
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "app.core.schema_check"],
        cwd=Path(__file__).resolve().parent.parent,
        env={**os.environ, "DATABASE_URL": url, "SCHEMA_DRIFT_MODE": "fail"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        "schema_check reported drift:\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
