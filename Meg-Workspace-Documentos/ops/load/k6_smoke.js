import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: Number(__ENV.VUS || 10),
  duration: __ENV.DURATION || '2m',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
  },
};

export default function () {
  const base = __ENV.BASE_URL;
  const token = __ENV.TOKEN;
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const ready = http.get(`${base}/ready`, { headers });
  check(ready, { 'ready endpoint responds': (r) => r.status === 200 });
  sleep(1);
}
