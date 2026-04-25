// Soak test — 30 VUs for 2 hours. Catches the failure modes that don't
// show up in a 10-minute baseline:
//
//   - Memory leaks (RSS climbing linearly)
//   - DB connection pool drift (slow reclaim → eventual exhaustion)
//   - JIT warmup wins evaporating (cache pollution)
//   - Long-running cron interference (KVKK anonymize @ 03:00 will fire
//     mid-run if you start around 01:00)
//
// Run quarterly or before a major release. Compare the JSON summary
// against the previous soak — drift, not absolute numbers, is the signal.

import { sleep } from 'k6';
import { assertNotProd, readEnv } from './lib/guard.js';
import { login } from './lib/auth.js';
import { dashboardFlow } from './scenarios/dashboard-flow.js';

export const options = {
  scenarios: {
    sustained_load: {
      executor: 'constant-vus',
      vus: 30,
      duration: '2h',
    },
  },
  thresholds: {
    // p95 should stay flat over 2 hours. Drift > 100ms vs the first
    // 10 minutes is the alarm.
    http_req_duration: ['p(95)<800'],
    http_req_failed: ['rate<0.02'],
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
  sleep(Math.random() * 4 + 3);
}
