// Login helper. Returns a Bearer token string suitable for Authorization
// headers, or aborts the test if login itself fails — there's no point
// generating load with an unauthenticated VU.
//
// The login endpoint is OAuth2-style x-www-form-urlencoded. Returns 200
// with {access_token, refresh_token, token_type}.

import http from 'k6/http';
import { check, fail } from 'k6';

export function login(baseUrl, email, password) {
  const url = `${baseUrl}/api/v1/auth/login`;
  const payload = {
    username: email,
    password: password,
  };
  const params = {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    tags: { name: 'auth_login' },
  };

  const res = http.post(url, payload, params);

  const ok = check(res, {
    'login status 200': (r) => r.status === 200,
    'login returns access_token': (r) => {
      try {
        const body = r.json();
        return body && typeof body.access_token === 'string';
      } catch {
        return false;
      }
    },
  });

  if (!ok) {
    fail(`login failed (status ${res.status}): ${res.body}`);
  }

  return res.json('access_token');
}

export function authHeaders(token) {
  return {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  };
}
