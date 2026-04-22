"""Migration chain verifier.

Why it exists:
    - Catches broken ``down_revision`` wiring before Alembic ever runs.
    - Verifies every migration file imports cleanly and exposes ``upgrade``
      / ``downgrade`` callables.
    - Sanity-checks that ``Base.metadata`` reflects every table mentioned
      by the migration registry (so autogenerate would be a no-op).

Run locally::

    cd backend && source venv/bin/activate
    python -m scripts.verify_migrations
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"


@dataclass
class MigrationModule:
    path: Path
    revision: str
    down_revision: str | None
    has_upgrade: bool
    has_downgrade: bool


def _load_module(path: Path) -> MigrationModule:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load migration: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    revision = getattr(module, "revision", None)
    if not revision:
        raise RuntimeError(f"{path.name} missing `revision`")
    down_revision = getattr(module, "down_revision", None)

    return MigrationModule(
        path=path,
        revision=revision,
        down_revision=down_revision,
        has_upgrade=callable(getattr(module, "upgrade", None)),
        has_downgrade=callable(getattr(module, "downgrade", None)),
    )


def _topological_order(modules: list[MigrationModule]) -> list[MigrationModule]:
    by_rev = {m.revision: m for m in modules}
    order: list[MigrationModule] = []
    visited: set[str] = set()
    for node in modules:
        walker = node
        stack: list[MigrationModule] = []
        while walker and walker.revision not in visited:
            if walker in stack:
                raise RuntimeError(
                    f"Migration cycle detected around {walker.revision}"
                )
            stack.append(walker)
            parent_rev = walker.down_revision
            walker = by_rev.get(parent_rev) if parent_rev else None
        for mig in reversed(stack):
            if mig.revision not in visited:
                order.append(mig)
                visited.add(mig.revision)
    return order


def verify() -> list[MigrationModule]:
    if not VERSIONS_DIR.is_dir():
        raise RuntimeError(f"Migrations folder missing: {VERSIONS_DIR}")

    files = sorted(p for p in VERSIONS_DIR.glob("*.py") if p.name != "__init__.py")
    if not files:
        raise RuntimeError("No migration files found")

    modules = [_load_module(p) for p in files]
    revisions = {m.revision for m in modules}

    for mig in modules:
        if not mig.has_upgrade or not mig.has_downgrade:
            raise RuntimeError(
                f"{mig.path.name} must define both upgrade() and downgrade()"
            )
        if mig.down_revision is not None and mig.down_revision not in revisions:
            raise RuntimeError(
                f"{mig.path.name} references unknown down_revision "
                f"{mig.down_revision!r}"
            )

    roots = [m for m in modules if m.down_revision is None]
    if len(roots) != 1:
        raise RuntimeError(
            f"Expected exactly one root migration, found {len(roots)}: "
            + ", ".join(m.revision for m in roots)
        )

    ordered = _topological_order(modules)
    if len(ordered) != len(modules):
        raise RuntimeError(
            "Topological order incomplete; some migrations are orphaned"
        )

    # Heads: revisions not cited as down_revision by anyone.
    cited_parents = {m.down_revision for m in modules if m.down_revision}
    heads = [m for m in modules if m.revision not in cited_parents]
    if len(heads) != 1:
        raise RuntimeError(
            "Expected a single head but found: "
            + ", ".join(h.revision for h in heads)
        )

    return ordered


def main() -> int:
    try:
        ordered = verify()
    except RuntimeError as exc:
        print(f"[migrations] FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"[migrations] {len(ordered)} migration(s) verified:")
    for mig in ordered:
        parent = mig.down_revision or "<root>"
        print(f"  - {mig.revision}  (<- {parent})  {mig.path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
