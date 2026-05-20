"""Round-15 N15-AUTH-3 / N15-AUTH-4 — dashboard + customer-health tenant guards.

Two cross-tenant leaks the Round-15 audit (`docs/audits/2026-05-20-cross-layer-audit-round15.md`)
identified:

  * **N15-AUTH-3** — ``backend/app/api/v1/dashboard.py`` aggregated
    revenue / quote / customer counts across every tenant. Any
    authenticated user reading ``GET /api/v1/dashboard/stats`` saw
    foreign-tenant totals. Patched so each aggregate filters on
    ``Model.tenant_id == current_user.tenant_id`` (``SparePart`` is the
    deliberate exception — the catalog is global by design).

  * **N15-AUTH-4** — ``CustomerHealthService.calculate_health_score`` /
    ``get_all_health_scores`` / ``get_at_risk_customers`` /
    ``predict_churn_risk`` accepted no tenant context. Routers under
    ``api/v1/customer_health.py``, ``cockpit.py:/risky-accounts``, and
    ``ai.py:/predict-churn`` declared ``current_user`` but never threaded
    it into the service. Patched: every entry point now takes a
    ``tenant_id`` kwarg, the service constrains the ``Customer`` lookup,
    and a cross-tenant lookup returns ``None`` (router converts to 404).

These are static-source checks — they hold the patches in place without
needing a live DB. Mirrors R14's source-shape gate at
``backend/tests/test_schema_drift.py:test_bootstrap_creates_every_model_table``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.services.customer_health_service import CustomerHealthService


_SERVICE_METHODS = frozenset({
    "calculate_health_score",
    "get_all_health_scores",
    "get_at_risk_customers",
    "predict_churn_risk",
})


def _service_calls_without_tenant_kwarg(source: str) -> list[str]:
    """Walk the AST and return every ``Health|service.<method>(...)``
    call that omits a ``tenant_id=`` keyword. Nesting (``max(limit * 3,
    limit)``) is handled correctly because we inspect the call's own
    keyword list, not the surrounding text.
    """
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in _SERVICE_METHODS:
            continue
        # Receiver name is ``health`` / ``service`` (instance) — skip
        # ``CustomerHealthService(self._db).<method>`` constructor chains
        # too, which are the account_aggregate_service form.
        if any(k.arg == "tenant_id" for k in node.keywords):
            continue
        offenders.append(ast.unparse(node))
    return offenders


_BACKEND_ROOT = Path(__file__).resolve().parent.parent / "app"


# ── N15-AUTH-3 — dashboard.py source-shape gate ──


_DASHBOARD = _BACKEND_ROOT / "api" / "v1" / "dashboard.py"


@pytest.mark.security
def test_n15_auth3_dashboard_threads_tenant_id() -> None:
    """``dashboard.py`` must thread ``current_user.tenant_id`` into every
    CRM aggregate. ``SparePart`` is the deliberate exception (global
    catalog — see model: no ``tenant_id`` column).

    Approach: split the file at each ``await db.execute(`` boundary and
    walk the executions. Every block that mentions an aggregate over
    EmailRequest / Quote / QuoteItem / Customer must also mention
    ``tenant_id`` somewhere in the same block. Blocks that touch only
    SparePart are skipped.
    """
    src = _DASHBOARD.read_text(encoding="utf-8")

    # Sanity: the canonical filter binding must be present (declared once
    # at the top of the handler and reused).
    assert "tenant_id = current_user.tenant_id" in src, (
        "dashboard.py must declare ``tenant_id = current_user.tenant_id`` "
        "and reuse it across queries (N15-AUTH-3)."
    )

    crm_models = ("EmailRequest", "Quote", "QuoteItem", "Customer")
    blocks = re.split(r"await db\.execute\(", src)
    # blocks[0] is the prefix before the first execute; skip.
    for block in blocks[1:]:
        # Truncate to the execute call's matching close — best effort by
        # taking the chunk up to the next ``await db.execute(`` or end.
        # ``tenant_id`` membership is what we actually care about.
        chunk = block[:800]  # plenty for the largest query in the file
        touched = next((m for m in crm_models if f"{m}." in chunk), None)
        if touched is None:
            continue  # SparePart-only block — global catalog, intentional.
        assert "tenant_id" in chunk, (
            f"dashboard.py aggregate over {touched} lacks a tenant filter "
            f"(N15-AUTH-3). Add ``.where({touched}.tenant_id == tenant_id)``."
        )


# ── N15-AUTH-4 — customer_health_service tenant kwarg gate ──


def test_n15_auth4_service_methods_accept_tenant_id() -> None:
    """The three public service entry points must accept ``tenant_id``.

    Run via introspection so the contract holds even if signatures grow
    additional kwargs later.
    """
    import inspect

    for method_name in (
        "calculate_health_score",
        "get_all_health_scores",
        "get_at_risk_customers",
        "predict_churn_risk",
    ):
        method = getattr(CustomerHealthService, method_name)
        sig = inspect.signature(method)
        assert "tenant_id" in sig.parameters, (
            f"CustomerHealthService.{method_name} must accept a "
            "``tenant_id`` kwarg (N15-AUTH-4)."
        )


_CUSTOMER_HEALTH_ROUTER = _BACKEND_ROOT / "api" / "v1" / "customer_health.py"
_AI_ROUTER = _BACKEND_ROOT / "api" / "v1" / "ai.py"
_COCKPIT_ROUTER = _BACKEND_ROOT / "api" / "v1" / "cockpit.py"


@pytest.mark.security
def test_n15_auth4_router_callers_thread_tenant_id() -> None:
    """Every router that drives ``CustomerHealthService`` must pass
    ``tenant_id=current_user.tenant_id`` (or equivalent ``user.tenant_id``).
    """
    for router_path, label in (
        (_CUSTOMER_HEALTH_ROUTER, "customer_health"),
        (_AI_ROUTER, "ai"),
        (_COCKPIT_ROUTER, "cockpit"),
    ):
        src = router_path.read_text(encoding="utf-8")
        offenders = _service_calls_without_tenant_kwarg(src)
        assert not offenders, (
            f"{label}.py calls CustomerHealthService without "
            f"``tenant_id=...`` — leaks cross-tenant data (N15-AUTH-4). "
            f"Offending calls: {offenders}"
        )


@pytest.mark.security
def test_n15_auth4_account_aggregate_threads_tenant_id() -> None:
    """``AccountAggregateService.refresh_enrichment`` and ``risk_summary``
    consume ``CustomerHealthService.calculate_health_score``; both must
    pass the ``user.tenant_id`` of the caller (not ``customer_id`` alone).
    """
    src = (
        _BACKEND_ROOT / "services" / "account_aggregate_service.py"
    ).read_text(encoding="utf-8")
    # AST-based — survives multi-line arg lists and nested calls.
    offenders = _service_calls_without_tenant_kwarg(src)
    assert not offenders, (
        "account_aggregate_service.calculate_health_score call lacks "
        f"``tenant_id=user.tenant_id`` (N15-AUTH-4). Offending: {offenders}"
    )
