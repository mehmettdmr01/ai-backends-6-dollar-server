'use strict';
const http = require('node:http');
const Database = require('better-sqlite3');

const db = new Database(process.env.SQLITE_PATH || 'seed/notes.db');
db.pragma('journal_mode = WAL');
db.pragma('synchronous = NORMAL');
db.pragma('busy_timeout = 5000');
db.pragma('cache_size = -16000');
db.pragma('mmap_size = 268435456');
db.pragma('temp_store = MEMORY');

const SEL = 'SELECT n.id AS id, u.username AS author, n.body AS body, n.created_at AS created_at FROM notes n JOIN users u ON u.id = n.user_id';
const qList = db.prepare(SEL + ' ORDER BY n.id DESC LIMIT 20');
const qOne = db.prepare(SEL + ' WHERE n.id = ?');
const qTok = db.prepare('SELECT id FROM users WHERE token = ?');
const qIns = db.prepare('INSERT INTO notes (user_id, body) VALUES (?, ?) RETURNING id');

const note = (r) => ({ id: r.id, author: r.author, body: r.body, created_at: r.created_at });
function send(res, code, str) {
  res.writeHead(code, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(str) });
  res.end(str);
}
const NF = '{"error":"not found"}', BADID = '{"error":"invalid id"}', UNAUTH = '{"error":"unauthorized"}',
  BADJSON = '{"error":"bad json"}', BADBODY = '{"error":"invalid body"}';

function handle(req, res) {
  try {
    let url = req.url; const q = url.indexOf('?'); if (q >= 0) url = url.slice(0, q);
    const m = req.method;
    if (url === '/health') {
      if (m !== 'GET') return send(res, 404, NF);
      return send(res, 200, '{"status":"ok"}');
    }
    if (url === '/notes') {
      if (m === 'GET') return send(res, 200, JSON.stringify({ notes: qList.all().map(note) }));
      if (m === 'POST') return post(req, res);
      return send(res, 404, NF);
    }
    if (url.startsWith('/notes/') && m === 'GET') {
      const s = url.slice(7);
      if (!/^[1-9][0-9]*$/.test(s)) {
        if (s.includes('/')) return send(res, 404, NF);
        return send(res, 400, BADID);
      }
      if (s.length > 15) return send(res, 404, NF);
      const r = qOne.get(Number(s));
      if (!r) return send(res, 404, NF);
      return send(res, 200, JSON.stringify({ note: note(r) }));
    }
    send(res, 404, NF);
  } catch (e) {
    send(res, 500, '{"error":"internal"}');
  }
}

function post(req, res) {
  const chunks = []; let size = 0, dead = false;
  req.on('data', (c) => {
    size += c.length;
    if (size > 65536) { dead = true; chunks.length = 0; send(res, 400, BADBODY); req.destroy(); return; }
    chunks.push(c);
  });
  req.on('end', () => {
    if (dead) return;
    try {
      const auth = req.headers.authorization;
      const mm = auth && /^Bearer\s+(\S+)\s*$/i.exec(auth);
      const u = mm ? qTok.get(mm[1]) : undefined;
      if (!u) return send(res, 401, UNAUTH);
      let j;
      try { j = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { return send(res, 400, BADJSON); }
      if (j === null || typeof j !== 'object' || Array.isArray(j) || typeof j.body !== 'string') return send(res, 400, BADBODY);
      const body = j.body.trim();
      if (body.length === 0 || (body.length > 250 && [...body].length > 500)) return send(res, 400, BADBODY);
      const id = qIns.get(u.id, body).id;
      send(res, 201, JSON.stringify({ note: note(qOne.get(id)) }));
    } catch (e) {
      send(res, 500, '{"error":"internal"}');
    }
  });
  req.on('error', () => {});
}

const server = http.createServer({ keepAlive: true, noDelay: true }, handle);
server.keepAliveTimeout = 120000;
server.headersTimeout = 125000;
server.requestTimeout = 0;
server.on('clientError', (e, sock) => { if (sock.writable) sock.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n'); else sock.destroy(); });
server.listen({ port: Number(process.env.PORT || 80), host: process.env.HOST || '0.0.0.0', backlog: 4096 });
process.on('uncaughtException', (e) => console.error(e));
