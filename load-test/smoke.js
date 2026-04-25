// Smoke test — 1 VU for 1 minute. Answers a single question:
// "Is this deployment alive enough to bother running real load tests?"
//
// Use as a pre-flight before baseline/stress/soak so you don't burn 10
// minutes of VU time discovering the staging DB is down.

import { sleep } from 'k6';
import { assertNotProd, readEnv } from './lib/guard.js';
import { login } from './lib/auth.js';
import { dashboardFlow } from './scenarios/dashboard-flow.js';

export const options = {
  vus: 1,
  duration: '1m',
  thresholds: {
    // No room for flake on smoke — every check must pass.
    checks: ['rate>0.99'],
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<2000'],
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
  sleep(1);
}
