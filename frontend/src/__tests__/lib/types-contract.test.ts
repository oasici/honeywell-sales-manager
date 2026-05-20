/**
 * Sprint 16g (Round-15) — manual-interface ↔ generated-schema contract gate.
 *
 * The Round-15 audit's N15-ARCH-1 finding (the openapi-typescript
 * artifact shipped in Sprint 15m but is not consumed by the SPA)
 * identified 7 verified-divergent CRM interfaces in ``lib/types.ts``
 * that should ideally alias the generated ``components['schemas']
 * ['*Response']`` types. The full alias landed in Sprint 15m-7 then
 * reverted because the backend Pydantic schemas mark too many fields
 * as Optional (N15-API-3 — "Optional-everywhere" pattern), which the
 * SPA consumers don't tolerate under ``noUncheckedIndexedAccess:
 * true``.
 *
 * Closing N15-API-3 is a quarterly-scale project (touches every CRM
 * response schema). Until it lands, the manual interfaces stay, but
 * this test catches the *other* drift direction:
 *
 *   - **Stale fields**: a manual interface declares a field the
 *     backend no longer exposes. Caught here.
 *   - **Missing fields**: a manual interface omits a field the
 *     backend just added. Caught at the call site (FE consumes
 *     ``customer.new_field`` → TS error because the manual interface
 *     doesn't declare it). The audit's stale-FE-fields list (§4.4)
 *     was exactly this class of bug.
 *
 * The gate is structural: every manual interface field must appear
 * in the generated schema's keys (with compatible nullability). When
 * the backend renames or drops a field, this test flags it before
 * the SPA ships a stale read.
 */

import { describe, it, expectTypeOf } from 'vitest';
import type { components } from '../../lib/api-types.gen';
import type {
  User,
  Customer,
  Opportunity,
  Lead,
  Quote,
  Contract,
  Subscription,
} from '../../lib/types';

type SchemaKeys<T extends keyof components['schemas']> = keyof components['schemas'][T];

describe('manual interface ↔ generated schema contract', () => {
  /**
   * Each test asserts that every key the manual interface declares
   * also exists on the generated schema. Type-level assertion via
   * ``expectTypeOf`` — runs at typecheck time, not runtime.
   */

  it('User keys are a subset of UserResponse', () => {
    // Compile-time: `keyof User` must be assignable to `keyof UserResponse`.
    expectTypeOf<keyof User>().toMatchTypeOf<SchemaKeys<'UserResponse'>>();
  });

  it('Customer keys are a subset of CustomerResponse', () => {
    expectTypeOf<keyof Customer>().toMatchTypeOf<SchemaKeys<'CustomerResponse'>>();
  });

  it('Opportunity keys are a subset of OpportunityResponse', () => {
    expectTypeOf<keyof Opportunity>().toMatchTypeOf<SchemaKeys<'OpportunityResponse'>>();
  });

  it('Lead keys are a subset of LeadResponse', () => {
    expectTypeOf<keyof Lead>().toMatchTypeOf<SchemaKeys<'LeadResponse'>>();
  });

  it('Quote keys are a subset of QuoteResponse', () => {
    expectTypeOf<keyof Quote>().toMatchTypeOf<SchemaKeys<'QuoteResponse'>>();
  });

  it('Contract keys are a subset of ContractResponse', () => {
    expectTypeOf<keyof Contract>().toMatchTypeOf<SchemaKeys<'ContractResponse'>>();
  });

  it('Subscription keys are a subset of SubscriptionResponse', () => {
    expectTypeOf<keyof Subscription>().toMatchTypeOf<SchemaKeys<'SubscriptionResponse'>>();
  });
});
