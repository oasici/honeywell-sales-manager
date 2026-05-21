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
