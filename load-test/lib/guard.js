// Guard rails for k6 scripts. Refuses to run against any URL that looks
// like production. The intent is defensive: a copy-paste error or a stale
// shell env var should not be enough to point a 500-VU stress test at the
// real backend.
//
// We bail at the top of every script's setup() so the abort happens before
// any HTTP traffic is generated.

import exec from 'k6/execution';

const PROD_PATTERNS = [
  /honeywell-backend\.onrender\.com$/i,
  /\bprod(uction)?\b/i,
];

export function assertNotProd(baseUrl) {
  if (!baseUrl) {
    throw new Error('BASE_URL env var is required');
  }
  for (const pattern of PROD_PATTERNS) {
    if (pattern.test(baseUrl)) {
      exec.test.abort(
        `BASE_URL "${baseUrl}" looks like production. ` +
        'Load tests must run against staging or a dedicated perf environment.'
      );
    }
  }
}

export function readEnv(name, fallback = undefined) {
  const value = __ENV[name];
  if (value === undefined || value === '') {
    if (fallback === undefined) {
      throw new Error(`Required env var ${name} is not set`);
    }
    return fallback;
  }
  return value;
}
