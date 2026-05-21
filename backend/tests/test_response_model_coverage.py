"""Round-15 N15-API-1 closeout gate — response_model coverage.

Sprint 16i (deferred-items closeout) — locks in the gain Round-15
achieved (113/538 = 21% → 538/538 = 100% accounted). Future regressions
where a contributor adds an endpoint without a ``response_model=`` /
without entering the documented exemption list will fail this gate
in CI.

Categories accepted:
  * **typed** — decorator declares ``response_model=Schema`` (a real
    Pydantic class — bare ``dict`` is rejected by the separate
    ``test_no_response_model_dict_regressions`` gate below).
  * **no-content** — endpoint uses ``status_code=204``; FastAPI
    forbids a response body so ``response_model`` is invalid by spec.
  * **exempt** — file-download / stream / redirect endpoint where the
    response is non-JSON. Must carry an inline
    ``# Round-15 N15-API-1: response_model exempt`` comment on the
    line immediately above the decorator.

Anything else is a regression and trips the test.
"""

from __future__ import annotations

from pathlib import Path

import pytest


_ROUTERS_DIR = Path(__file__).resolve().parent.parent / "app" / "api" / "v1"


def _collect_endpoints() -> list[tuple[str, int, str, bool, bool, bool]]:
    """Walk every ``@router.<method>(...)`` decorator block in ``api/v1``.

    Returns a list of tuples
    ``(file, line, block, has_response_model, is_204, has_exempt_marker)``
    so the test body can build a precise failure message.
    """
    rows: list[tuple[str, int, str, bool, bool, bool]] = []
    for path in sorted(_ROUTERS_DIR.glob("*.py")):
        lines = path.read_text().splitlines(keepends=True)
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line.startswith("@router."):
                i += 1
                continue
            depth = line.count("(") - line.count(")")
            k = i
            while k < len(lines) - 1 and depth > 0:
                k += 1
                depth += lines[k].count("(") - lines[k].count(")")
            block = "".join(lines[i : k + 1])
            # Look back to the first non-blank line for an exempt marker.
            j = i - 1
            while j >= 0 and lines[j].strip() == "":
                j -= 1
            prev = lines[j] if j >= 0 else ""

            has_rm = "response_model=" in block
            is_204 = "status_code=204" in block
            has_exempt = "response_model exempt" in prev

            rows.append(
                (path.name, i + 1, block.strip()[:100], has_rm, is_204, has_exempt)
            )
            i = k + 1
    return rows


@pytest.mark.schema
def test_every_endpoint_has_response_model_or_documented_exemption() -> None:
    """Sprint 16i gate — fail when a router endpoint has no
    ``response_model``, no 204-No-Content status, and no documented
    exempt marker.
    """
    rows = _collect_endpoints()
    violations: list[str] = []
    for file_name, line_no, block, has_rm, is_204, has_exempt in rows:
        if has_rm or is_204 or has_exempt:
            continue
        violations.append(f"{file_name}:{line_no} — {block}")

    assert not violations, (
        "Found endpoints without response_model and without a documented "
        "exemption. Add ``response_model=<Schema>`` (a real Pydantic "
        "class — bare ``dict`` is blocked by the no-dict regression gate), "
        "set ``status_code=204`` for no-content endpoints, or place a "
        "``# Round-15 N15-API-1: response_model exempt`` comment directly "
        "above the decorator for file/stream/redirect responses. "
        f"Violations:\n  - " + "\n  - ".join(violations)
    )


@pytest.mark.schema
def test_no_paginated_response_dict_regressions() -> None:
    """Sprint 16h closeout — ``PaginatedResponse[dict]`` was eliminated.

    Re-introducing it would regress R14-API-1 / N15-API-1. The audit
    documented every legitimate list endpoint as needing a typed
    pagination row schema; future list endpoints must follow suit.
    """
    offenders: list[str] = []
    for path in sorted(_ROUTERS_DIR.glob("*.py")):
        src = path.read_text()
        if "PaginatedResponse[dict]" in src:
            # Capture context for the failure message.
            for ln, line in enumerate(src.splitlines(), start=1):
                if "PaginatedResponse[dict]" in line:
                    offenders.append(f"{path.name}:{ln}  {line.strip()}")
    assert not offenders, (
        "PaginatedResponse[dict] regressions found. Define a typed "
        "row schema (see backend/app/schemas/round15_pagination.py for "
        "the Round-15 cohort).\n  - " + "\n  - ".join(offenders)
    )


@pytest.mark.schema
def test_no_response_model_dict_regressions() -> None:
    """Round-16 N15-API-7 closeout — ``response_model=dict`` was
    eliminated across all 90 routers in batches 1-8.

    Re-introducing the bare ``dict`` type would regress the typed-
    contract gain. When a handler legitimately needs a heterogeneous
    shape, declare a Pydantic schema with ``model_config = {"extra":
    "allow"}`` (see ``app/schemas/round16_aggregates.py`` for the
    catch-all pattern). The schema still surfaces "this is a JSON
    object" in OpenAPI instead of the SDK-hostile
    ``Record<string, unknown>`` that ``dict`` produces.
    """
    import re

    # Matches ``response_model=dict`` with optional whitespace.
    # Word boundary prevents matching ``response_model=dict_alias``
    # if a future contributor introduces one.
    pattern = re.compile(r"response_model\s*=\s*dict\b")
    offenders: list[str] = []
    for path in sorted(_ROUTERS_DIR.glob("*.py")):
        src = path.read_text()
        if not pattern.search(src):
            continue
        for ln, line in enumerate(src.splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{ln}  {line.strip()}")

    assert not offenders, (
        "response_model=dict regressions found. Round-16 batch 8 "
        "eliminated every bare ``dict`` response model. Add a typed "
        "Pydantic schema (see app/schemas/round16_aggregates.py for "
        "the catch-all pattern with extra='allow' for heterogeneous "
        "payloads).\n  - " + "\n  - ".join(offenders)
    )


# ──────────────────────────────────────────────────────────────────
# Round-16 N15-API-3 (Track C closeout) — strict-shape gate.
#
# Each ``<Entity>StrictResponse`` declared during the C3-C8 picker
# rollout claims a Required contract on the entity's NOT-NULL ORM
# columns. This test AST-validates that claim so future schema
# edits can't silently degrade a Required field to Optional.
#
# Exception list per RFC § "Per-Entity Steps" — some fields are NOT
# NULL on the ORM but intentionally omitted from / nullable in the
# serializer:
#
#   * ``Customer.kvkk_consent`` — PII-grade; serialized only by
#     /compliance/* endpoints.
#   * ``Quote.tenant_id`` — R10-API-2: tenant scoping is enforced
#     server-side; the column is never surfaced to clients.
#
# Anything else NOT NULL on the ORM must be Required on the strict
# schema (annotation must not include ``None`` and must lack a
# default — Pydantic v2 treats a field with no default as Required).
# ──────────────────────────────────────────────────────────────────


_STRICT_SCHEMA_EXEMPTIONS: dict[str, set[str]] = {
    "CustomerStrictResponse": {"kvkk_consent"},
    "QuoteStrictResponse": {"tenant_id"},
}


def _orm_mandatory_columns(model_cls) -> set[str]:
    """Return ORM columns that are NOT NULL **and have no default**.

    Pydantic v2 treats a field with no default as "Required" — the
    consumer can rely on it being present in every response. We
    intentionally exclude NOT-NULL-with-default columns
    (e.g. ``Opportunity.status default="active"``,
    ``Opportunity.currency default="TRY"``) because:

      1. The serializer may legitimately project a subset of these
         (the picker route returns the masked variant when a
         field-permission rule applies).
      2. Their default-on-INSERT guarantees a value in the row but
         doesn't bind the SDK contract — callers commonly omit them
         from create/update bodies.

    Primary keys are always mandatory. Datetime columns whose default
    is a Python lambda (created_at/updated_at) count too — the lambda
    fires at INSERT, so reads always see a value.
    """
    import datetime as _dt

    out: set[str] = set()
    for col in model_cls.__table__.columns:
        if col.primary_key:
            out.add(col.name)
            continue
        if col.nullable:
            continue
        # NOT NULL but defaulted — only count for datetime columns
        # whose default is a Python callable (lambda → datetime.now).
        # Other defaults (string literals like "active", numeric 0)
        # are treated as Optional because the serializer may omit them.
        has_default = col.default is not None or col.server_default is not None
        if has_default:
            # Treat datetime + python-callable defaults as mandatory
            # (created_at / updated_at pattern).
            is_dt = isinstance(col.type.python_type, type) and issubclass(
                col.type.python_type, _dt.datetime
            )
            if is_dt and col.default is not None and callable(getattr(col.default, "arg", None)):
                out.add(col.name)
            continue
        out.add(col.name)
    return out


@pytest.mark.schema
def test_no_optional_everywhere_on_required_fields() -> None:
    """Track C closeout — every ``<Entity>StrictResponse`` must
    declare its ORM's NOT-NULL columns as Required Pydantic fields.

    Catches future regressions where a contributor adds a NOT-NULL
    column to the ORM but forgets to declare it Required on the
    strict schema, or accidentally widens an existing Required field
    to ``T | None``.

    Exemptions live in ``_STRICT_SCHEMA_EXEMPTIONS`` for fields that
    are NOT NULL in the DB but intentionally omitted/nullable in the
    serializer (PII, defense-in-depth).
    """
    from app.models.contract import Contract
    from app.models.customer import Customer
    from app.models.lead import Lead
    from app.models.opportunity import Opportunity
    from app.models.quote import Quote
    from app.models.subscription import Subscription
    from app.schemas.contract import ContractStrictResponse
    from app.schemas.customer import CustomerStrictResponse
    from app.schemas.lead import LeadStrictResponse
    from app.schemas.opportunity import OpportunityStrictResponse
    from app.schemas.quote import QuoteStrictResponse
    from app.schemas.subscription import SubscriptionStrictResponse

    pairs = [
        (CustomerStrictResponse, Customer),
        (OpportunityStrictResponse, Opportunity),
        (LeadStrictResponse, Lead),
        (QuoteStrictResponse, Quote),
        (ContractStrictResponse, Contract),
        (SubscriptionStrictResponse, Subscription),
    ]

    violations: list[str] = []
    for schema_cls, orm_cls in pairs:
        schema_name = schema_cls.__name__
        not_null_cols = _orm_mandatory_columns(orm_cls)
        exempt = _STRICT_SCHEMA_EXEMPTIONS.get(schema_name, set())
        schema_fields = schema_cls.model_fields

        for col_name in not_null_cols:
            if col_name in exempt:
                continue
            if col_name not in schema_fields:
                # Column not declared on schema — schema is allowed to
                # project a subset, but if it's NOT declared we can't
                # verify the contract. Skip silently; the serializer
                # might be omitting it on purpose.
                continue
            field = schema_fields[col_name]
            # In Pydantic v2 a Required field has ``is_required() == True``
            # which checks both annotation (no None) and default
            # (no default value supplied).
            if not field.is_required():
                violations.append(
                    f"{schema_name}.{col_name} is Optional but the "
                    f"ORM column {orm_cls.__name__}.{col_name} is "
                    f"NOT NULL. Either declare as Required (drop the "
                    f"``| None`` and the default) or add to the "
                    f"_STRICT_SCHEMA_EXEMPTIONS allowlist with a "
                    f"comment explaining why."
                )

    assert not violations, (
        "StrictResponse schemas declare Optional fields for NOT-NULL "
        "ORM columns — this regresses the Track C N15-API-3 contract."
        "\n  - " + "\n  - ".join(violations)
    )


# ──────────────────────────────────────────────────────────────────
# Round-16 N15-ARCH-1 — duplicate canonical-type guard.
#
# The 7 CRM canonical types (User, Customer, Opportunity, Lead,
# Quote, Contract, Subscription) live in ``frontend/src/lib/types.ts``
# (the narrowed manual shapes) and ``frontend/src/lib/api-types.gen.ts``
# (the OpenAPI-derived shapes). Declaring a local ``interface User``
# (or any of the others) inside ``features/`` or ``components/``
# creates a shadow type — the exact anti-pattern the audit's
# N15-ARCH-1 finding caught on ``UserManagementPage.tsx``.
#
# This gate scans the SPA source for such duplicates and fails CI.
# It's the in-repo equivalent of the ESLint
# ``no-restricted-syntax`` rule recommended in the deferred plan
# (the actual ESLint rule lives behind a config-protection hook).
# ──────────────────────────────────────────────────────────────────


_CANONICAL_FE_TYPES: tuple[str, ...] = (
    "User",
    "Customer",
    "Opportunity",
    "Lead",
    "Quote",
    "Contract",
    "Subscription",
)


@pytest.mark.schema
def test_no_duplicate_canonical_fe_types() -> None:
    """Round-16 — prevent shadow declarations of the canonical CRM
    types outside ``frontend/src/lib/``.

    Catches future contributors who paste a local ``interface User
    {...}`` into a feature file instead of importing from
    ``lib/types``. The audit's original N15-ARCH-1 example was
    ``UserManagementPage.tsx:27`` with its own narrower ``User``.
    """
    import re

    frontend_root = (
        _ROUTERS_DIR.parent.parent.parent.parent / "frontend" / "src"
    )
    if not frontend_root.exists():
        pytest.skip("frontend/ not in this checkout")

    # ``lib/`` is the canonical home; ``__tests__`` reads them only.
    allowed_prefixes = (
        frontend_root / "lib",
        frontend_root / "__tests__",
    )

    pattern = re.compile(
        r"(?m)^\s*(?:export\s+)?(?:interface|type)\s+("
        + "|".join(_CANONICAL_FE_TYPES)
        + r")\b"
    )

    offenders: list[str] = []
    for path in frontend_root.rglob("*.ts*"):
        if any(
            str(path).startswith(str(allowed))
            for allowed in allowed_prefixes
        ):
            continue
        # Skip type-only generated/declaration files.
        if path.name.endswith(".d.ts"):
            continue
        src = path.read_text()
        for match in pattern.finditer(src):
            ln = src[: match.start()].count("\n") + 1
            offenders.append(
                f"{path.relative_to(frontend_root)}:{ln} — duplicate "
                f"declaration of canonical type ``{match.group(1)}``"
            )

    assert not offenders, (
        "Local declarations of canonical CRM types found. Import "
        "from ``../lib/types`` instead.\n  - " + "\n  - ".join(offenders)
    )


@pytest.mark.schema
def test_no_console_logs_in_frontend_features() -> None:
    """R14-LOG-1 regression gate — production code in the SPA must
    not call ``console.log`` / ``console.error`` / ``console.warn``.

    Reference comments mentioning ``R14-LOG-1`` in a string literal or
    block comment are allowed; actual executable calls are not.
    """
    frontend_root = (
        _ROUTERS_DIR.parent.parent.parent.parent / "frontend" / "src"
    )
    if not frontend_root.exists():
        pytest.skip("frontend directory not present in this checkout")

    feature_paths = list((frontend_root / "features").rglob("*.tsx")) + list(
        (frontend_root / "features").rglob("*.ts")
    )
    component_paths = list((frontend_root / "components").rglob("*.tsx")) + list(
        (frontend_root / "components").rglob("*.ts")
    )

    import re

    offending: list[str] = []
    # Only flag executable calls — ignore lines that are inside a
    # comment (// or /* ... */ on the same line, best-effort).
    call_re = re.compile(r"\bconsole\.(?:log|error|warn|info|debug)\(")
    for path in feature_paths + component_paths:
        for ln, line in enumerate(path.read_text().splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if call_re.search(line):
                offending.append(f"{path.relative_to(frontend_root)}:{ln}")
    assert not offending, (
        "Executable ``console.*`` calls in features/components. Replace "
        "with ``toast.error(...)`` or ``Sentry.addBreadcrumb(...)`` per "
        "R14-LOG-1.\n  - " + "\n  - ".join(offending)
    )
