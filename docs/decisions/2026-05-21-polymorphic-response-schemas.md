# RFC — Polymorphic Response Schemas for CRM Entities

**Status.** Draft, Sprint 16 Track C1 (from [`2026-05-21-round-16-deferred-plan.md`](../audits/2026-05-21-round-16-deferred-plan.md)). Awaiting tech-lead + PM read.
**Author.** Engineering.
**Date.** 2026-05-21.
**Audit reference.** [`2026-05-20-cross-layer-audit-round15.md`](../audits/2026-05-20-cross-layer-audit-round15.md) § N15-API-3.

---

## Problem Statement

Every CRM Pydantic response schema (`CustomerResponse`, `OpportunityResponse`, `LeadResponse`, `QuoteResponse`, `ContractResponse`, `SubscriptionResponse`, `InvoiceResponse`, `UserResponse`) currently marks **every field as Optional**:

```python
class CustomerResponse(BaseModel):
    id: int
    name: str | None = None      # ← actually NOT NULL in DB
    email: str | None = None     # ← actually nullable (fine)
    tenant_id: int | None = None  # ← actually NOT NULL in DB
    # ... 25 more fields all Optional
    model_config = {"from_attributes": True, "extra": "allow"}
```

The intent is documented at [`schemas/customer.py:65-79`](../../backend/app/schemas/customer.py#L65-L79): the `apply_request_perms` masking layer (see [`services/field_permission_service.py:285-296`](../../backend/app/services/field_permission_service.py#L285-L296)) can REMOVE fields entirely from a serializer's output when an admin marks them `hidden`. Pydantic would fail validation if the schema declares a Required field and the field is absent, so every field becomes Optional defensively.

This forces a contract weakness:

1. **SDK consumers must null-check unnecessarily.** Even `id` is Optional. The SPA compensates with `??` fallbacks at 10+ catalogued sites ([audit §4.3](../audits/2026-05-20-cross-layer-audit-round15.md#43-hardcoded-fallbacks-masking-missing-data)).
2. **Sprint 15m-7 attempted to alias the SPA's manual interfaces to `components['schemas']['*Response']` and reverted** because the SPA compiles with `noUncheckedIndexedAccess: true` and chokes on the loose Optional-everywhere shape.
3. **Manual interfaces in `lib/types.ts` drift from backend** (Round-15 audit §4.4 catalogued 8 stale FE field references the contract didn't document).

The Round-15 audit classified this as a "HIGH severity contract weakness" and recommended a quarterly-scale fix.

---

## Goals

1. SDK consumers (FE, third-party) can rely on a NOT-NULL contract for fields the database guarantees.
2. The field-level masking pattern (`hidden` / `masked` rules in `field_permission_service`) keeps working — operator-configured PII protection is non-negotiable.
3. `lib/types.ts` manual interfaces can be replaced with `components['schemas']['*Response']` aliases (closes the audit's N15-ARCH-1 codemod blocker).
4. No silent breakage: every existing API consumer continues to work or fails loudly with a Pydantic validation error that points at the specific drift.

---

## Non-Goals

- Changing the field-permission rules themselves (admin-configured allowlists stay).
- Re-deriving NOT NULL guarantees from production data (use the existing ORM declarations as the source of truth — `Mapped[int]` is NOT NULL, `Mapped[int | None]` is nullable).
- Reverting `apply_request_perms` masking semantics.

---

## Candidate Solutions

### Option A — Two-schema split (audit-recommended)

```python
class CustomerResponse(BaseModel):
    """Wire shape when no field masking is active."""
    id: int                      # required
    name: str                    # required (DB NOT NULL)
    tenant_id: int               # required (DB NOT NULL)
    email: str | None = None     # nullable in DB → Optional
    # ... only nullable fields stay Optional


class CustomerMaskedResponse(BaseModel):
    """Wire shape when one or more fields are masked / hidden.

    All NOT-NULL fields become Optional because ``hidden`` access
    removes them from the dict; ``masked`` access replaces them with
    a sentinel string. Both cases mean the consumer cannot rely on
    presence.
    """
    id: int                      # required — ``id`` itself is never masked
    name: str | None = None
    tenant_id: int | None = None
    # ... matches today's schema


# Router picks the variant based on whether the current request has
# any active masking rules:
@router.get("/", response_model=CustomerResponse | CustomerMaskedResponse)
async def list_customers(...):
    ...
```

**Pros.**
- Honest contract: when masking is off (the common case), consumers get the strong shape.
- Clean OpenAPI: each schema lists its own fields explicitly.
- The SPA codemod becomes mechanical: alias to `CustomerResponse` and accept that admins with masking rules occasionally get the looser shape.

**Cons.**
- Doubles the schema count (8 entities × 2 = 16 schemas in `components.schemas`).
- Every router must thread "is masking active for this request?" into the response decision. Existing code uses `apply_request_perms(data, "customer")` after serialization — it doesn't know if anything was actually masked.
- OpenAPI `oneOf` codegen quality varies (TypeScript handles it; some SDK generators don't).

### Option B — Single schema with conditional Required via `discriminator`

```python
class CustomerResponse(BaseModel):
    """Single schema; nullability matches the DB NOT NULL declarations.

    The masking layer is moved BEFORE serialization: when a field is
    masked or hidden, the handler raises HTTPException(403) with a
    "fields_masked" detail array instead of silently returning a
    partial response. SPA renders a "permission required" panel.
    """
    id: int
    name: str
    tenant_id: int
    email: str | None = None
    ...
```

**Pros.**
- Single source of truth.
- Cleanest SDK type.

**Cons.**
- **Breaks the masking UX.** Today an SPA user with `customer.name` masked sees `"name": "***"` and the rest of the customer normally. Under Option B they'd see a 403 and no data at all. Product/Legal would reject this — KVKK masking is explicitly partial.
- Doesn't actually close the problem; just hides it behind a different status code.

**Verdict.** Reject — UX regression too large.

### Option C — Field-level `Required[...]` + per-request schema-override

Use Pydantic v2's `Required[...]` to mark which fields are guaranteed, then dynamically downgrade the schema in the router:

```python
from typing import Annotated
from pydantic import Field

class CustomerResponse(BaseModel):
    id: Annotated[int, Field(description="Always present")]
    name: Annotated[str, Field(description="Required unless masked")]
    tenant_id: Annotated[int, Field(description="Required unless masked")]
    email: str | None = None  # always optional


# Router builds a per-request response_model that downgrades the
# Required fields to Optional iff masking is active:
@router.get("/")
async def list_customers(
    masking_active: bool = Depends(_has_active_masking_rules),
    ...
):
    schema = CustomerResponse if not masking_active else _make_masked(CustomerResponse)
    return Response(content=..., media_type="application/json")
```

**Pros.**
- Single schema declared statically; OpenAPI lists the strong shape.
- No double-schema bookkeeping.

**Cons.**
- OpenAPI documents the strong shape but the actual response may be weaker. Worse than Option A for SDK truthfulness.
- Requires custom `response_model` resolution per request — FastAPI doesn't support this natively; need a `Response` override.
- Loses FastAPI's automatic response validation (which catches serializer drift today).

**Verdict.** Reject — gives up too much existing safety.

---

## Recommendation

**Option A (two-schema split)**, with these caveats:

1. **Detect masking presence cheaply.** Add a `_has_masking_rules_for(entity_type)` helper that reads the request-scoped `_FIELD_PERMS_CV` and returns `bool`. O(1). The router then picks the schema:
   ```python
   if _has_masking_rules_for("customer"):
       return CustomerMaskedResponse.model_validate(data)
   return CustomerResponse.model_validate(data)
   ```
2. **Route the picker through a single helper**, not per-router code:
   ```python
   def _customer_response_model(request: Request) -> type[BaseModel]:
       return CustomerMaskedResponse if _has_masking_rules_for("customer") else CustomerResponse

   @router.get("/", response_model_by_alias=True)
   async def list_customers(
       resp_model = Depends(_customer_response_model),
       ...
   ):
       items = [_customer_to_dict(c) for c in customers]
       return PaginatedResponse[resp_model](items=items, ...)
   ```
   (Sketch — actual API needs work; FastAPI dependency-injected response_model isn't first-class.)
3. **Migrate one entity at a time.** Customer is the canary because it has the most call sites and the most masking rules. Per-entity rollout per [`2026-05-21-16g-codemod-plan.md`](../audits/2026-05-21-16g-codemod-plan.md).
4. **Lock the gain.** Once an entity is migrated, extend `test_response_model_coverage.py` with `test_no_optional_on_required_<entity>_fields` that AST-checks the strict schema declares every ORM NOT-NULL field as required.

---

## Migration Order

Mirrors the codemod plan in [`2026-05-21-16g-codemod-plan.md`](../audits/2026-05-21-16g-codemod-plan.md) § "Migration order":

| Step | Entity | Effort | Notes |
|---|---|---|---|
| C2 | **Customer** | 3 days | Canary; biggest blast radius |
| C3 | Opportunity | 3 days | High call-site count |
| C4 | Lead | 2 days | Smaller surface |
| C5 | Quote | 2 days | `QuoteStatus` literal narrowing benefit |
| C6 | Contract | 2 days | Embedded customer summary nested schema |
| C7 | Subscription | 2 days | Enum-shaped fields |
| C8 | User | 2 days | Auth-store hydration consideration |

Estimated total: 16 dev-days (~3 calendar weeks at 1 engineer, ~2 weeks at 2 engineers in parallel after C2).

---

## Per-Entity Steps (template)

For each entity:

1. **Backend.**
   1. In `schemas/<entity>.py`, rename the current `<Entity>Response` to `<Entity>MaskedResponse`.
   2. Create a new `<Entity>Response` with Required nullability matching the ORM (`Mapped[int]` → `int`, `Mapped[int | None]` → `int | None`).
   3. Add the `_<entity>_response_model` picker (or use the shared helper from a new `app.services.response_model_picker` module).
   4. Update every router endpoint that returns the entity:
      - `response_model=<Entity>Response` (the strong shape).
      - Use the picker if masking can be active for this route.
2. **Tests.**
   1. Add `test_<entity>_response_strong_when_no_masking` — drives a route without masking config, asserts response shape includes Required fields.
   2. Add `test_<entity>_response_masked_when_masking_active` — drives a route with a masking rule, asserts response uses the masked variant.
   3. Add `test_no_optional_on_required_<entity>_fields` — AST gate to prevent future regression.
3. **Frontend.**
   1. Regenerate `frontend/src/lib/api-types.gen.ts` (`bash scripts/generate-api-types.sh`).
   2. Drop the manual `interface <Entity>` from `frontend/src/lib/types.ts`.
   3. Add `export type <Entity> = components['schemas']['<Entity>Response']` (or `... | components['schemas']['<Entity>MaskedResponse']` if any masking-active route is in the consumer set).
   4. Run `npx tsc --noEmit --pretty false`. Fix every call-site that relied on the manual shape.
4. **Verification.**
   1. `pytest backend/tests/test_response_model_coverage.py tests/test_<entity>_response.py`.
   2. `cd frontend && npx tsc --noEmit && npx vitest run`.
   3. E2E smoke: `pnpm e2e --grep <entity>`.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| FastAPI doesn't natively support per-request `response_model` selection | Use a custom `Response` subclass or `response_model_by_alias` + manual `model_validate`. Spike during Sprint C2 to confirm API. |
| Doubling schema count bloats `api-types.gen.ts` | Acceptable — file is ~38k lines and grows linearly with schema count. The trade-off (correctness > size) is favorable. |
| Old SDK clients still expect the loose shape | Releases are versioned; bump to 2.x and note in CHANGELOG. SPA on `deploy/render-sandbox` regenerates types automatically. |
| Migration takes longer than 3 weeks | Stop after Customer + Opportunity if scope grows; the canary covers ~70% of high-traffic call sites. |
| Masking presence detection has request overhead | `_FIELD_PERMS_CV` is a `ContextVar` — O(1) get. Negligible. |

---

## Open Questions

1. **Sub-entity nested types** (`customer: { id, name, company }` embedded in `OpportunityResponse`). Should these get the two-schema treatment too, or stay as a single shape? Recommendation: stay single. Embeds are denormalized snapshots; masking on the embedded customer is the parent's responsibility.
2. **Computed fields** (`pinned`, `quote_count`, `total_quote_value`, `rotting_days`). These are emitted by `extras="allow"` today; in the new schemas they should be declared Optional. Recommendation: declare explicitly with `Annotated[..., Field(description="Computed; not stored")]`.
3. **Legacy `tenant_id: int | None`** on schemas where the ORM is NOT NULL. Today's masking can't `hidden` tenant_id (it's auth-load-bearing), so the strong schema can mark it Required. Confirm with security team.

---

## Acceptance

RFC accepted when:
- [ ] Tech-lead signs off on Option A as the chosen direction.
- [ ] PM agrees to the 3-week calendar carve-out (or accepts the "stop after canary" fallback).
- [ ] Spike on FastAPI per-request response_model selection lands and confirms the picker approach is viable.

Once accepted, schedule C2 (Customer canary) as the first sprint of Round-17.

---

— end RFC
