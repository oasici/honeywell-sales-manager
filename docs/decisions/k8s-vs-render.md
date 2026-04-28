# ADR — Kubernetes vs. Render production target

**Status**: Accepted
**Date**: 2026-04-28
**Authors**: Platform team
**Closes**: V3 sandbox commit `b0fc471` shipped K8s manifests; this ADR
decides whether we promote them to production or deprecate.

---

## Context

The V3 platform expansion (`feat(sandbox): v3 platform expansion`,
2026-04-23) added Kubernetes manifests under
`k8s/base`, `k8s/overlays`, `k8s/jobs`. Production currently runs on
**Render** (web + worker + scheduler services), declared in
`render.yaml` and deployed via GitHub Actions.

V9 framework analysis flagged a P3 gap: **no decision exists** on
whether the K8s scaffolding gets promoted, archived, or actively
maintained. Engineers have to either keep both deployment models green
(double cost) or pick one.

## Decision

**Stay on Render. Move K8s manifests to `k8s/_archive/` with a
README explaining the history. Do not remove — sandbox or
self-hosted users may still want them.**

## Rationale

Render covers 100% of our current production needs:

- **Scale**: Render auto-scales web workers; we are not bound on CPU
  or RAM. The k8s autoscaler we'd need (HPA + VPA) costs more
  operational overhead than we save.
- **Region**: single-region (Frankfurt) is fine — no customer
  contract requires multi-region right now. K8s would only matter
  when that changes.
- **Operations**: Render absorbs the runbook surface (DNS, certs,
  metrics, logs, restarts). Running our own EKS/GKE adds 1-2 FTE.
- **CI/CD**: deploy via Render's Git integration is single-click;
  K8s would require Helm chart maintenance + ArgoCD or similar.

K8s would buy us:

- True multi-cluster / multi-region (needed if we win an EU + US
  enterprise contract simultaneously)
- Custom operators (e.g. tenant-isolated namespaces — relevant for
  V8 multi-tenant CRM if we go that direction)
- BYO-Cloud deployments — some enterprise customers may require
  running in their AWS/Azure subscription

None of those are pressing yet.

## Consequences

### Immediate
- `k8s/` moves to `k8s/_archive/` with a README pointing at the
  Render setup as the live deployment target.
- CI workflows that lint K8s manifests get unwired.
- `feature-flags.md` already uses Render env vars; no doc change
  needed there.

### Future (revisit triggers)
The decision flips back to "go K8s" when **any** of these hit:

1. A customer contract requires multi-region active-active.
2. A customer requires BYO-Cloud (their AWS/Azure tenant).
3. We onboard ≥3 high-traffic tenants and Render's scaling
   characteristics become a bottleneck.
4. Cost analysis shows K8s + managed control plane (~$700/mo) is
   cheaper than Render at our scale.

When this happens, the archived manifests are the starting point;
we re-validate them against the then-current model + extract Helm
chart patterns from the V3 work.

## Alternatives considered

### Alt 1: Run both
Cost: 2× deployment surface. Rejected — no upside that justifies
maintaining two production targets.

### Alt 2: Delete K8s manifests outright
Cost: Lose sandbox / self-hosted preset. Rejected — the manifests
encode learnings (resource limits, init containers, secret
mounting) that we'd otherwise re-discover when the trigger hits.

### Alt 3: Move to Fly.io / Northflank / similar
Cost: Migration effort with marginal gain over Render. Rejected.

## Action items

- [ ] Move `k8s/` → `k8s/_archive/`
- [ ] Add `k8s/_archive/README.md` with the trigger list above
- [ ] Update root `README.md` "Deployment" section to point at Render
      only (one-liner)
- [ ] Close V9 Sprint Q in `docs/v9-v2-v3-gap-closure-plan.md`

This ADR is the source-of-truth for the Render-only decision until a
trigger above flips us back to K8s.
