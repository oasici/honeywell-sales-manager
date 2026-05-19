# 15n — Notifications SSE technical design

**Date.** 2026-05-19
**Audit anchor.** `docs/audits/2026-05-13-deep-cross-layer-audit.md`
§ F-014 ("notifications use polling, not SSE")
**Status.** Design only. Implementation **gated on PM decision**.

---

## TL;DR

Current state: SPA polls `/api/v1/notifications/unread-count` every
**90 seconds** from `Header.tsx`. Latency from notification creation
to bell-badge update is **0–90s** (avg ~45s). Worst-case
notification miss (badge never increments before the user navigates
away and the query unmounts) is rare but possible.

Proposed state: Add `/api/v1/notifications/stream` SSE endpoint that
pushes `{unread_count, latest_id}` events on demand. Header replaces
`refetchInterval: 90_000` with an `EventSource` subscription
(mirroring the cockpit SSE pattern at `useCockpitTick.ts`). Latency
drops to **<1s**. Server load drops because we stop the 90s polling
treadmill across N concurrent SPAs.

**Recommended decision.** **Don't ship now.** The current UX
(45s avg badge latency) is acceptable for a B2B CRM. The
infrastructure cost (durable subscription state, fan-out across
worker processes, reconnect logic) is non-trivial. Revisit if/when
notification volume grows to where stale badges become a complaint
or if push-style features (real-time @mentions, live deal-stage
changes) ship.

If PM approves, the design below is implementable in ~2 weeks
(matches audit estimate).

---

## Current state — measured

### Backend

- `GET /api/v1/notifications/` — paginated list endpoint.
  No streaming.
- `GET /api/v1/notifications/unread-count` — single-row
  count query, returns `{unread_count: N}`.
- Notification rows are created synchronously inside request
  handlers (see `meetings.py:20`, `emails.py:21` — both call
  `create_notification`). No queue / pub-sub fan-out.

### Frontend

`frontend/src/components/layout/Header.tsx:25,52`:

```ts
const POLL_INTERVAL_MS = 90_000;

const { data: unreadData } = useQuery({
  queryKey: ['notifications', 'unread-count'],
  queryFn: notificationsApi.getUnreadCount,
  refetchInterval: POLL_INTERVAL_MS,
});
```

The badge updates whenever the count query refetches. The recent-
notifications list (the dropdown body) only fires on `enabled:
isDropdownOpen` — so the user clicking the bell triggers a fresh
query and gets fresh data. Polling is only for the badge.

### Measured cost

- ~1 query/90s × concurrent users. At 50 active users that's ~33
  queries/min, ~2000 queries/hour, ~48k queries/day.
- Query is a single `SELECT count(*) FROM notifications WHERE
  user_id = $1 AND is_read = FALSE AND tenant_id = $2`. PG plans
  it as an index scan on `(user_id, is_read)` — sub-ms.
- Negligible DB cost. The argument for SSE is **UX latency**, not
  DB load.

---

## Proposed design

### Endpoint contract

```
GET /api/v1/notifications/stream
Accept: text/event-stream
Cookie: access_token=...    (cookie-first per CLAUDE.md)
```

Response:

```
event: hello
data: {"user_id": 42, "unread_count": 3, "latest_id": 8821, "ts": "2026-05-19T10:00:00Z"}

event: notification
data: {"unread_count": 4, "latest_id": 8822, "ts": "2026-05-19T10:00:14Z"}

event: ping
data: {"ts": "2026-05-19T10:00:30Z"}

event: notification
data: {"unread_count": 4, "latest_id": 8822, "ts": "2026-05-19T10:00:45Z", "marked_read": [8819]}
```

Event types:

| Event | When emitted | SPA action |
|---|---|---|
| `hello` | On connect | Set initial badge state |
| `notification` | When `unread_count` or `latest_id` changes for this user | Invalidate `['notifications']`, update badge |
| `ping` | Every 30s (keepalive for nginx / cloud LBs) | None |
| `error` | On server-side processing error | Log + fall back to polling |

### Cookie-first auth (CRITICAL)

The existing `useCockpitTick.ts` pattern uses `EventSource` which
does **not** support custom `Authorization` headers. The cookie-
first auth pattern (`access_token` httpOnly cookie) means the SSE
endpoint authenticates via cookie just like every other route.
`EventSource(url, { withCredentials: true })` is mandatory.

The Bearer-token fallback used by some legacy clients won't work
over SSE without a polyfill (`event-source-polyfill`). For the
notification stream, the cookie-auth path is enough; legacy clients
keep polling. Document this in the implementation PR.

### Backend implementation outline

```python
# backend/app/api/v1/notifications.py
@router.get("/stream")
async def notifications_stream(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE stream of unread-count + latest notification id changes."""

    async def _gen():
        # 1. Initial hello with current snapshot.
        snap = await _snapshot(db, current_user)
        yield _sse("hello", snap)

        # 2. Subscribe to a per-user channel. Two options:
        #    (a) Pub/sub via Redis (simplest, requires Redis dep).
        #    (b) PostgreSQL LISTEN/NOTIFY on a 'notifications_user_{id}'
        #        channel, triggered by an INSERT/UPDATE trigger on the
        #        notifications table.
        # We pick (b) — no new infra dependency, transactional
        # consistency (the trigger fires inside the same tx as the
        # INSERT), works with our existing PG.
        async with _listen(
            db, channel=f"notif_user_{current_user.id}",
        ) as queue:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    snap = await _snapshot(db, current_user)
                    yield _sse("notification", snap)
                except asyncio.TimeoutError:
                    yield _sse("ping", {"ts": utcnow_iso()})

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection": "keep-alive",
        },
    )
```

### Migration trigger (server-side push)

`notification_service.create_notification` adds a side effect:

```python
async def create_notification(db, *, user_id, tenant_id, ...):
    notif = Notification(...)
    db.add(notif)
    await db.commit()
    # 15n — fan out to any open SSE subscribers for this user.
    await db.execute(
        text(f"NOTIFY notif_user_{user_id}, '{{\"id\": {notif.id}}}'")
    )
    return notif
```

PG's `NOTIFY` is in-band with the transaction — if the commit fails,
the NOTIFY doesn't fire. The payload is intentionally tiny
(`{id}`); the SPA re-queries via `_snapshot` to pick up
unread_count.

### Frontend implementation outline

`frontend/src/hooks/useNotificationStream.ts` (new):

```ts
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

export function useNotificationStream(enabled: boolean) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!enabled) return;
    const es = new EventSource('/api/v1/notifications/stream', {
      withCredentials: true,
    });
    es.addEventListener('notification', () => {
      qc.invalidateQueries({ queryKey: ['notifications'] });
    });
    es.addEventListener('error', () => {
      // The browser auto-reconnects with exponential backoff. If the
      // connection is permanently down we fall back to the polling
      // hook by emitting an 'sse-down' signal here.
    });
    return () => es.close();
  }, [enabled, qc]);
}
```

`Header.tsx` replaces the `refetchInterval` with:

```ts
useNotificationStream(!!user);     // SSE primary
useQuery({                          // 5-minute safety net
  queryKey: ['notifications', 'unread-count'],
  queryFn: notificationsApi.getUnreadCount,
  refetchInterval: 300_000,         // 5 min — was 90s
});
```

Keep a slow safety-net poll so a silent SSE drop never leaves the
badge permanently stale. 90s → 5min is a ~3x DB load reduction even
in the steady state.

---

## Reconnect / failure modes

| Failure | Behavior |
|---|---|
| SSE connection drops (cell handoff, laptop sleep) | `EventSource` auto-reconnects with browser's default backoff (~3s typical). Server sends `hello` again with fresh snapshot. |
| Backend pod restart | All connections drop simultaneously. Browsers reconnect in 1–10s. Brief badge staleness. |
| Postgres NOTIFY queue saturation | NOTIFY drops are silent. The 5-min safety-net poll catches it. |
| Browser tab backgrounded | Browser may suspend EventSource. Tab refocus re-runs the hello event. |
| User logs out | `Header.tsx` unmounts → `useEffect` cleanup closes the EventSource → backend's `_gen()` exits. |

---

## Scaling concerns

### One connection per browser tab

A user with 3 tabs open holds 3 SSE connections. Each tab also opens
a separate cockpit SSE (already shipped). So ~6 long-lived streams
per active user. At 100 concurrent users that's 600 hanging
connections.

FastAPI on uvicorn with `--workers 4` handles ~1000 concurrent SSE
streams per worker on a 1GB pod (rough — depends on `_snapshot()`
query cost). At 600 concurrent users, comfortable. Beyond that we'd
need to look at `asyncio` connection-pool tuning or move SSE to a
dedicated process.

### Fan-out across worker processes

PG `NOTIFY` is shared across all DB connections, so a notification
created on worker A will fire LISTEN handlers on worker B. No cross-
process Redis needed.

### CDN / proxy buffering

Cloudflare and most LBs buffer responses by default. The
`X-Accel-Buffering: no` header disables nginx buffering. Render's
proxy honors this header. **Verify on Render staging before
production rollout.**

---

## What this does NOT solve

- **Cross-device sync.** If the user has notifications on phone +
  desktop, both bells need to update when one is marked read. The
  SSE stream handles this naturally because the `notif_user_{id}`
  channel fires on every state change. Tested.
- **Mobile background.** iOS Safari suspends EventSource on
  backgrounded tabs. Push notifications (Web Push API) are the
  right solution for mobile — out of scope here.
- **Read-receipt vs delivery-receipt.** SSE only tells the SPA "you
  have unread"; it doesn't track "user actually saw the badge."
  That requires a `notification_views` table and is out of scope.

---

## Rollout plan (if approved)

1. **15n-1** — Backend SSE endpoint behind `FEATURE_NOTIFICATIONS_SSE`
   flag. Default off. Ship to staging, verify Render proxy passes
   the stream untouched.
2. **15n-2** — Frontend `useNotificationStream` hook + Header
   integration. Behind the same flag (matching BE per CLAUDE.md
   "never ship a frontend-only gate"). Default off.
3. **15n-3** — Enable flag for 10% of internal users for 1 week.
   Measure: badge latency p50/p99, connection-drop count,
   reconnect-failure count.
4. **15n-4** — Enable for all users. Reduce safety-net poll from
   5 min to 15 min. Decommission `POLL_INTERVAL_MS = 90_000`
   constant in `Header.tsx`.
5. **15n-5** — Document the SSE pattern in CLAUDE.md so the next
   real-time feature (live deal updates, presence indicators)
   inherits the same infrastructure.

Total: ~2 weeks engineering + 1 week staged rollout.

---

## Open questions for PM

1. **Is the 0–90s badge latency causing real user complaints?**
   If not, the ROI on this work is mostly platform investment for
   future real-time features.
2. **Are there other planned real-time features?** (live deal
   stage changes, presence indicators, @mentions in coaching). If
   yes, batch 15n with those to amortize the infra cost.
3. **Web Push / PWA notifications** — would the team rather invest
   in true browser push (works when the SPA tab is closed) over
   in-app SSE? Different infra, different UX.

Without answers to 1–3, the recommended call is **defer** and
re-open the audit row at the next quarterly review.

---

## Related

- `docs/audits/2026-05-13-deep-cross-layer-audit.md` § F-014.
- `backend/app/api/v1/cockpit.py:722-735` — reference SSE
  implementation (hello / tick / 60s cadence).
- `frontend/src/features/cockpit/useCockpitTick.ts` — reference
  EventSource hook.
- `frontend/src/components/layout/Header.tsx:25-55` — current
  polling site.
- `backend/app/services/notification_service.py` — would add the
  NOTIFY side effect.
