// The load test. One virtual user clicks once every 5 to 15 seconds, so 10 users are about 1 request per second.
// Clicks: 70 % newest notes, 20 % one random note, 10 % write a note.
//   k6 run -e BASE_URL=http://10.0.0.2 -e VUS=5000 -e RAMP=60s -e HOLD=5m -e TOKENS=seed/tokens.json yuk.js
import http from 'k6/http';
import { sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { SharedArray } from 'k6/data';

const BASE = __ENV.BASE_URL;
const VUS = Number(__ENV.VUS);
const NOTES = Number(__ENV.NOTES || 1000000);
const tokens = new SharedArray('tokens', () => JSON.parse(open(__ENV.TOKENS)));
const created = new Counter('notes_created');

export const options = {
  discardResponseBodies: true,
  scenarios: {
    users: {
      executor: 'ramping-vus',
      startVUs: 0,
      gracefulRampDown: '5s',
      stages: [
        { duration: __ENV.RAMP || '60s', target: VUS },
        { duration: __ENV.HOLD || '5m', target: VUS },
        { duration: '10s', target: 0 },
      ],
    },
  },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
};

// Scenario start time on this machine, so a probe's clock can be turned into a number of users.
export function setup() { console.log('RAMP_START ' + Date.now() / 1000); }

export default function () {
  sleep(5 + Math.random() * 10);
  const dice = Math.random();
  if (dice < 0.7) {
    http.get(`${BASE}/notes`, { tags: { name: 'GET /notes' } });
  } else if (dice < 0.9) {
    http.get(`${BASE}/notes/${1 + Math.floor(Math.random() * NOTES)}`, { tags: { name: 'GET /notes/:id' } });
  } else {
    const t = tokens[(__VU - 1) % tokens.length].token;
    const r = http.post(`${BASE}/notes`, JSON.stringify({ body: `note from user ${__VU}, click ${__ITER}` }),
      { headers: { Authorization: `Bearer ${t}`, 'Content-Type': 'application/json' }, tags: { name: 'POST /notes' } });
    if (r.status === 201) created.add(1);
  }
}
