'use strict';
// A server whose capacity we know in advance, to test the rig instead of a contestant. Each request burns exactly 1 ms
// of CPU on one thread, so it cannot exceed about 1,000 requests a second, which is about 10,000 users at one click in
// 10 seconds. If the rig reports something far from that, the rig is wrong. It answers without touching the database.
const http = require('http');
const burn = () => { const end = process.hrtime.bigint() + 1000000n; while (process.hrtime.bigint() < end); };
const server = http.createServer((req, res) => {
  req.resume();
  req.on('end', () => {
    burn();
    res.writeHead(req.method === 'POST' ? 201 : 200, { 'Content-Type': 'application/json' });
    res.end('{"status":"ok"}');
  });
});
server.keepAliveTimeout = 65000;
server.headersTimeout = 66000;
server.listen(Number(process.env.PORT), process.env.HOST);
