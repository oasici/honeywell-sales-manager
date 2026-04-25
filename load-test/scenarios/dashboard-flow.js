// Typical dashboard user journey: list opportunities → drill into one →
// list customers → pull a board.
//
// This is the read-heavy path that 80% of users follow most of the day.
// Hitting it under load surfaces N+1 queries, missing indexes, and
// unbounded list endpoints faster than synthetic /health pings.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { authHeaders } from '../lib/auth.js';

export function dashboardFlow(baseUrl, token) {
  const auth = authHeaders(token);

  // 1) Opportunities list (homepage default)
  let res = http.get(
    `${baseUrl}/api/v1/opportunities/?limit=20`,
    { ...auth, tags: { name: 'opportunities_list' } },
  );
  check(res, { 'opps list 200': (r) => r.status === 200 });
  sleep(1);

  // 2) Pull customers list
  res = http.get(
    `${baseUrl}/api/v1/customers/?limit=20`,
    { ...auth, tags: { name: 'customers_list' } },
  );
  check(res, { 'customers list 200': (r) => r.status === 200 });
  sleep(0.5);

  // 3) Board (kanban view) — typically heavier than the list
  res = http.get(
    `${baseUrl}/api/v1/opportunities/board`,
    { ...auth, tags: { name: 'opportunities_board' } },
  );
  // 200 or 404 (feature flag off) both acceptable; real failure is 5xx
  check(res, { 'board not 5xx': (r) => r.status < 500 });
  sleep(1);

  // 4) Health endpoint — cheap, ensures the deployment is responsive
  res = http.get(`${baseUrl}/api/health`, { tags: { name: 'health' } });
  check(res, { 'health 200': (r) => r.status === 200 });
}
