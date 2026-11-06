'use strict';

// This intentionally uses node:http rather than a web framework.  On this API the
// database calls are the useful work; avoiding framework parsing and routing leaves
// more of the single CPU available for SQLite and JSON serialization.
const http = require('node:http');
const Database = require('better-sqlite3');

const dbPath = process.env.SQLITE_PATH;
if (!dbPath) {
  console.error('SQLITE_PATH is required');
  process.exit(1);
}

const db = new Database(dbPath);
// The seed is already WAL, but set the operational properties explicitly so a
// newly copied database behaves the same way.  NORMAL makes a committed WAL
// transaction durable without paying an fsync for every click.
db.pragma('journal_mode = WAL');
db.pragma('synchronous = NORMAL');
db.pragma('busy_timeout = 2500');
db.pragma('wal_autocheckpoint = 1000');
db.pragma('cache_size = -4096');
db.pragma('temp_store = MEMORY');
// Mmap uses the kernel page cache rather than eagerly allocating this much RAM.
db.pragma('mmap_size = 268435456');

const listNotes = db.prepare(
  'SELECT n.id, u.username AS author, n.body, n.created_at ' +
  'FROM notes AS n JOIN users AS u ON u.id = n.user_id ' +
  'ORDER BY n.id DESC LIMIT 20'
);
const getNote = db.prepare(
  'SELECT n.id, u.username AS author, n.body, n.created_at ' +
  'FROM notes AS n JOIN users AS u ON u.id = n.user_id WHERE n.id = ?'
);
// Token lookup is deliberately a query for every POST: tokens are never cached.
const getUserForToken = db.prepare('SELECT id, username FROM users WHERE token = ?');
const insertNote = db.prepare(
  'INSERT INTO notes (user_id, body) VALUES (?, ?) ' +
  'RETURNING id, body, created_at'
);

const JSON_TYPE = 'application/json';
const healthBody = '{"status":"ok"}';
const badIdBody = '{"error":"invalid id"}';
const notFoundBody = '{"error":"not found"}';
const unauthorizedBody = '{"error":"unauthorized"}';
const badJsonBody = '{"error":"bad json"}';
const invalidBody = '{"error":"invalid body"}';
const MAX_REQUEST_BYTES = 16384;

function send(res, status, body) {
  res.writeHead(status, {
    'Content-Type': JSON_TYPE,
    'Content-Length': Buffer.byteLength(body),
  });
  res.end(body);
}

function pathOf(url) {
  const question = url.indexOf('?');
  return question === -1 ? url : url.slice(0, question);
}

function validId(path) {
  const match = /^\/notes\/(\d+)$/.exec(path);
  if (!match) return null;
  // Bind as a BigInt so a very large decimal input cannot silently round to a
  // different ID. SQLite rowids are signed 64-bit integers.
  let id;
  try { id = BigInt(match[1]); } catch { return undefined; }
  if (id < 1n || id > 9223372036854775807n) return undefined;
  return id;
}

function readBody(req, done) {
  let size = 0;
  const chunks = [];
  let rejected = false;
  req.on('data', (chunk) => {
    if (rejected) return;
    size += chunk.length;
    if (size > MAX_REQUEST_BYTES) {
      rejected = true;
      chunks.length = 0;
      return;
    }
    chunks.push(chunk);
  });
  req.on('end', () => done(rejected ? null : Buffer.concat(chunks).toString('utf8'), rejected));
  req.on('aborted', () => done(null, true));
  req.on('error', () => done(null, true));
}

function characterCount(value) {
  // SQLite's length(TEXT) counts Unicode characters, rather than UTF-16 units.
  // Array.from has the same code-point behavior, including emoji.
  return Array.from(value).length;
}

function handlePost(req, res) {
  const authorization = req.headers.authorization;
  const prefix = 'Bearer ';
  if (typeof authorization !== 'string' || !authorization.startsWith(prefix) || authorization.length === prefix.length) {
    req.resume();
    send(res, 401, unauthorizedBody);
    return;
  }

  // Authentication is intentionally completed before attaching a JSON parser.
  // This gives an invalid token 401 even if it accompanies malformed JSON.
  let user;
  try {
    user = getUserForToken.get(authorization.slice(prefix.length));
  } catch {
    req.resume();
    send(res, 401, unauthorizedBody);
    return;
  }
  if (!user) {
    req.resume();
    send(res, 401, unauthorizedBody);
    return;
  }

  readBody(req, (raw, oversized) => {
    if (res.writableEnded) return;
    if (oversized) {
      send(res, 400, invalidBody);
      return;
    }
    let input;
    try {
      input = JSON.parse(raw);
    } catch {
      send(res, 400, badJsonBody);
      return;
    }
    if (!input || typeof input.body !== 'string') {
      send(res, 400, invalidBody);
      return;
    }
    const body = input.body.trim();
    if (body.length === 0 || characterCount(body) > 500) {
      send(res, 400, invalidBody);
      return;
    }
    try {
      const created = insertNote.get(user.id, body);
      // Property order is part of the API contract.
      const note = {
        id: created.id,
        author: user.username,
        body: created.body,
        created_at: created.created_at,
      };
      send(res, 201, '{"note":' + JSON.stringify(note) + '}');
    } catch (error) {
      // A constraint error should be unreachable after validation, but never let
      // malformed input take down the single process.
      send(res, 400, invalidBody);
    }
  });
}

function handle(req, res) {
  const path = pathOf(req.url || '');
  if (req.method === 'GET' && path === '/health') {
    send(res, 200, healthBody);
    return;
  }
  if (req.method === 'GET' && path === '/notes') {
    try {
      send(res, 200, '{"notes":' + JSON.stringify(listNotes.all()) + '}');
    } catch {
      send(res, 500, '{"error":"internal server error"}');
    }
    return;
  }
  if (req.method === 'GET') {
    const id = validId(path);
    if (path.startsWith('/notes/')) {
      // A /notes/<anything> route has an ID-shaped error; unrelated routes 404.
      if (id === null || id === undefined) {
        send(res, 400, badIdBody);
        return;
      }
    }
    if (id === undefined) {
      send(res, 404, notFoundBody);
      return;
    }
    if (id !== null) {
      try {
        const note = getNote.get(id);
        if (!note) send(res, 404, notFoundBody);
        else send(res, 200, '{"note":' + JSON.stringify(note) + '}');
      } catch {
        send(res, 404, notFoundBody);
      }
      return;
    }
  }
  if (req.method === 'POST' && path === '/notes') {
    handlePost(req, res);
    return;
  }
  send(res, 404, notFoundBody);
}

const server = http.createServer({ keepAlive: true, maxHeaderSize: 8192 }, handle);
server.keepAliveTimeout = 65000;
server.headersTimeout = 70000;
server.requestTimeout = 10000;
server.maxRequestsPerSocket = 0;
// Do not retain a second copy of request bodies in Node's parser buffer.
server.on('clientError', (error, socket) => socket.destroy());

const host = process.env.HOST || '0.0.0.0';
const port = Number(process.env.PORT || 80);
server.listen(port, host, () => console.log(`listening on ${host}:${port}`));

function shutdown() {
  server.close(() => db.close());
  // Stop accepting new work immediately; an active SQLite transaction has already
  // committed by the time a 201 was sent.
  setTimeout(() => process.exit(0), 5000).unref();
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
