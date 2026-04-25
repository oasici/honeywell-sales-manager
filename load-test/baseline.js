// Baseline — 50 VUs for 10 minutes. Models typical production load on
// a Tuesday afternoon. Sets the perf benchmark we regress against.
//
// Thresholds match the SLO published in docs/SLO.md:
//   - p95 latency < 500ms
//   - error rate < 1%
//
// Breach exits non-zero so CI can fail the weekly run.

import { sleep } from 'k6';
import { assertNotProd, readEnv } from './lib/guard.js';
import { login } from './lib/auth.js';
import { dashboardFlow } from './scenarios/dashboard-flow.js';

export const options = {
  scenarios: {
    typical_load: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 50 },  // ramp up
        { duration: '10m', target: 50 }, // sustain
        { duration: '2m', target: 0 },   // ramp down
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
  },
};

const BASE_URL = readEnv('BASE_URL');
const EMAIL = readEnv('TEST_USER_EMAIL');
const PASSWORD = readEnv('TEST_USER_PASSWORD');

export function setup() {
  assertNotProd(BASE_URL);
  const token = login(BASE_URL, EMAIL, PASSWORD);
  return { token };
}

export default function (data) {
  dashboardFlow(BASE_URL, data.token);
  // Realistic think time between page loads. Without this we'd be
  // simulating 50 robots, not 50 humans, and the perf numbers would
  // be misleading.
  sleep(Math.random() * 3 + 2);
}
