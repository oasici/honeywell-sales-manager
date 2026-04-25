// Stress test — ramps from 100 to 500 VUs to find the breaking point.
//
// Unlike baseline, the goal here is NOT to stay under SLO — we expect
// thresholds to breach somewhere in the ramp. The result is a number:
// "the deployment falls over at ~N concurrent users." Plug that into
// capacity planning.
//
// Run sparingly. 500 VUs for 10 minutes against a free Render tier
// will exhaust the DB pool and trigger the breaker. That's the point.

import { sleep } from 'k6';
import { assertNotProd, readEnv } from './lib/guard.js';
import { login } from './lib/auth.js';
import { dashboardFlow } from './scenarios/dashboard-flow.js';

export const options = {
  scenarios: {
    breaking_point: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 100 },
        { duration: '5m', target: 100 },
        { duration: '2m', target: 250 },
        { duration: '5m', target: 250 },
        { duration: '2m', target: 500 },
        { duration: '5m', target: 500 },
        { duration: '2m', target: 0 },
      ],
      gracefulRampDown: '30s',
    },
  },
  // Looser thresholds — we expect this run to hurt. Use them as
  // "service still partially usable" markers, not pass/fail SLO checks.
  thresholds: {
    http_req_duration: ['p(95)<3000'],
    http_req_failed: ['rate<0.10'],
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
  sleep(Math.random() * 2 + 1);
}
