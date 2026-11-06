'use strict';
const http = require('node:http');
const { DatabaseSync } = require('node:sqlite');

const db = new DatabaseSync(process.env.SQLITE_PATH || 'seed/notes.db');
db.exec('PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000; PRAGMA cache_size=-65536; PRAGMA mmap_size=268435456; PRAGMA temp_store=MEMORY;');

const COLS = 'SELECT n.id AS id, u.username AS author, n.body AS body, n.created_at AS created_at FROM notes n JOIN users u ON u.id=n.user_id';
const qList = db.prepare(COLS + ' ORDER BY n.id DESC LIMIT 20');
const qOne = db.prepare(COLS + ' WHERE n.id=?');
const qTok = db.prepare('SELECT id, username FROM users WHERE token=?');
const qIns = db.prepare('INSERT INTO notes (user_id, body) VALUES (?, ?) RETURNING id, created_at');

const noteJson = (r) => '{"id":' + r.id + ',"author":' + JSON.stringify(r.author) + ',"body":' + JSON.stringify(r.body) + ',"created_at":' + JSON.stringify(r.created_at) + '}';

function send(res, code, s) {
  res.writeHead(code, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(s) });
  res.end(s);
}
const NF = '{"error":"not found"}';

function handle(req, res) {
  const url = req.url;
  const q = url.indexOf('?');
  const path = q < 0 ? url : url.slice(0, q);
  const m = req.method;
  try {
    if (path === '/health') {
      if (m === 'GET') return send(res, 200, '{"status":"ok"}');
    } else if (path === '/notes') {
      if (m === 'GET') {
        const rows = qList.all();
        return send(res, 200, '{"notes":[' + rows.map(noteJson).join(',') + ']}');
      }
      if (m === 'POST') return post(req, res);
    } else if (path.startsWith('/notes/') && m === 'GET') {
      const id = path.slice(7);
      if (!/^[0-9]+$/.test(id) || /^0+$/.test(id)) return send(res, 400, '{"error":"invalid id"}');
      if (id.length > 15) return send(res, 404, NF);
      const r = qOne.get(Number(id));
      if (!r) return send(res, 404, NF);
      return send(res, 200, '{"note":' + noteJson(r) + '}');
    }
    send(res, 404, NF);
  } catch (e) {
    console.error(e);
    try { send(res, 500, '{"error":"internal"}'); } catch {}
  }
}

function post(req, res) {
  const auth = req.headers.authorization;
  let user;
  if (auth) {
    const mm = /^Bearer (.+)$/i.exec(auth);
    if (mm) user = qTok.get(mm[1].trim());
  }
  if (!user) { req.resume(); return send(res, 401, '{"error":"unauthorized"}'); }
  const chunks = [];
  let size = 0, big = false;
  req.on('data', (c) => { size += c.length; if (size > 65536) big = true; else chunks.push(c); });
  req.on('end', () => {
    try {
      if (big) return send(res, 400, '{"error":"invalid body"}');
      let j;
      try { j = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { return send(res, 400, '{"error":"bad json"}'); }
      const b = j !== null && typeof j === 'object' && !Array.isArray(j) ? j.body : undefined;
      if (typeof b !== 'string') return send(res, 400, '{"error":"invalid body"}');
      const t = b.trim();
      if (t.length === 0 || (t.length > 500 && [...t].length > 500)) return send(res, 400, '{"error":"invalid body"}');
      const r = qIns.get(user.id, t);
      send(res, 201, '{"note":' + noteJson({ id: r.id, author: user.username, body: t, created_at: r.created_at }) + '}');
    } catch (e) {
      console.error(e);
      try { send(res, 500, '{"error":"internal"}'); } catch {}
    }
  });
}

const server = http.createServer({ keepAlive: true, noDelay: true }, handle);
server.keepAliveTimeout = 120000;
server.headersTimeout = 125000;
server.requestTimeout = 0;
server.listen({ port: Number(process.env.PORT || 80), host: process.env.HOST || '0.0.0.0', backlog: 8192 });
process.on('SIGTERM', () => { try { db.close(); } catch {} process.exit(0); });
process.on('uncaughtException', (e) => console.error(e));
