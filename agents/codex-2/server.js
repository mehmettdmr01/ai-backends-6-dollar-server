'use strict';

// Deliberately use node:http instead of a framework: this endpoint is tiny and
// spends nearly all useful time in SQLite, while avoiding per-request framework
// allocations is valuable on the small target VM.
const http = require('node:http');
const Database = require('better-sqlite3');
const utf8 = new TextDecoder('utf-8', { fatal: true });

const dbPath = process.env.SQLITE_PATH;
if (!dbPath) {
  throw new Error('SQLITE_PATH is required');
}

const db = new Database(dbPath);
// The supplied database is already WAL, but set these explicitly so a copied
// database has the durability and concurrency properties required by the spec.
db.pragma('journal_mode = WAL');
db.pragma('synchronous = NORMAL');
db.pragma('busy_timeout = 5000');
// Keep SQLite's private heap modest. The kernel page cache and mmap serve the
// large, mostly-read database without duplicating a large cache in this process.
db.pragma('cache_size = -16384');
db.pragma('mmap_size = 536870912');

// Construct the hot list response in SQLite's C implementation. It is still a
// fresh SQL read every time, but avoids allocating 20 JS objects and encoding
// them again for the endpoint that accounts for most benchmark traffic.
const newestNotesJSON = db.prepare(
  "SELECT '{\"notes\":' || COALESCE(json_group_array(" +
  "json_object('id', id, 'author', author, 'body', body, 'created_at', created_at)), '[]') || '}' AS result " +
  'FROM (SELECT n.id, u.username AS author, n.body, n.created_at ' +
  'FROM notes AS n JOIN users AS u ON u.id = n.user_id ORDER BY n.id DESC LIMIT 20)'
).pluck();
const noteByIdJSON = db.prepare(
  "SELECT json_object('note', json_object('id', n.id, 'author', u.username, " +
  "'body', n.body, 'created_at', n.created_at)) AS result " +
  'FROM notes AS n JOIN users AS u ON u.id = n.user_id WHERE n.id = ?'
).pluck();
const userByToken = db.prepare('SELECT id, username FROM users WHERE token = ?');
const insertNote = db.prepare(
  'INSERT INTO notes (user_id, body) VALUES (?, ?) ' +
  'RETURNING id, body, created_at'
);

const JSON_TYPE = 'application/json; charset=utf-8';
const health = '{"status":"ok"}';
const notFound = '{"error":"not found"}';
const invalidId = '{"error":"invalid id"}';
const unauthorized = '{"error":"unauthorized"}';
const badJson = '{"error":"bad json"}';
const invalidBody = '{"error":"invalid body"}';

function send(res, status, text) {
  res.writeHead(status, {
    'Content-Type': JSON_TYPE,
    'Content-Length': Buffer.byteLength(text),
  });
  res.end(text);
}

function noteJSON(note) {
  // Object property insertion order is the API's requested order.
  return JSON.stringify({
    id: note.id,
    author: note.author,
    body: note.body,
    created_at: note.created_at,
  });
}

function bearerToken(header) {
  if (typeof header !== 'string' || !header.startsWith('Bearer ')) return null;
  const token = header.slice(7);
  return token.length ? token : null;
}

function handlePost(req, res) {
  // Authentication deliberately precedes body handling, including malformed
  // bodies, as required by the API contract.
  const token = bearerToken(req.headers.authorization);
  const user = token === null ? undefined : userByToken.get(token);
  if (!user) {
    send(res, 401, unauthorized);
    // Do not retain a potentially large unauthorised request body in memory.
    req.resume();
    return;
  }

  const chunks = [];
  let tooLarge = false;
  let bodyBytes = 0;
  // Valid API bodies are at most a little over 500 UTF-8 characters. This
  // ceiling protects the 1 GB VM from many concurrent malicious uploads.
  const maxBodyBytes = 64 * 1024;
  req.on('data', (chunk) => {
    if (!tooLarge) {
      bodyBytes += chunk.length;
      if (bodyBytes > maxBodyBytes) {
        tooLarge = true;
        chunks.length = 0;
      } else {
        chunks.push(chunk);
      }
    }
  });
  req.on('end', () => {
    if (tooLarge) {
      send(res, 400, invalidBody);
      return;
    }
    let value;
    try {
      // Fatal decoding rejects malformed UTF-8 instead of silently replacing
      // bytes with U+FFFD and accidentally accepting a non-JSON payload.
      const raw = utf8.decode(Buffer.concat(chunks, bodyBytes));
      value = JSON.parse(raw);
    } catch {
      send(res, 400, badJson);
      return;
    }
    if (!value || typeof value.body !== 'string') {
      send(res, 400, invalidBody);
      return;
    }
    const body = value.body.trim();
    let characters = 0;
    // SQLite length(TEXT) counts Unicode characters rather than UTF-16 code
    // units, so keep validation consistent for non-BMP input such as emoji.
    for (const _ of body) characters++;
    if (characters === 0 || characters > 500) {
      send(res, 400, invalidBody);
      return;
    }
    const created = insertNote.get(user.id, body);
    send(res, 201, '{"note":' + noteJSON({
      id: created.id,
      author: user.username,
      body: created.body,
      created_at: created.created_at,
    }) + '}');
  });
  req.on('error', () => {
    if (!res.headersSent) res.destroy();
  });
}

const server = http.createServer((req, res) => {
  // Ignore a query component for normal HTTP route semantics without allocating
  // a URL object on every request.
  const rawUrl = req.url || '';
  const query = rawUrl.indexOf('?');
  const path = query === -1 ? rawUrl : rawUrl.slice(0, query);

  if (req.method === 'GET' && path === '/health') {
    send(res, 200, health);
    return;
  }
  if (req.method === 'GET' && path === '/notes') {
    send(res, 200, newestNotesJSON.get());
    return;
  }
  if (req.method === 'GET' && path.startsWith('/notes/')) {
    const id = path.slice(7);
    // /notes/:id is a one-segment route; deeper paths (and a missing segment)
    // are unknown routes rather than malformed note identifiers.
    if (id.length === 0 || id.includes('/')) {
      send(res, 404, notFound);
      return;
    }
    if (!/^[1-9][0-9]*$/.test(id)) {
      send(res, 400, invalidId);
      return;
    }
    const note = noteByIdJSON.get(id);
    if (note === undefined) {
      send(res, 404, notFound);
      return;
    }
    send(res, 200, note);
    return;
  }
  if (req.method === 'POST' && path === '/notes') {
    handlePost(req, res);
    return;
  }
  send(res, 404, notFound);
});

// Slow/incomplete requests must not occupy thousands of connection objects on
// the shared 1 GB VM. A generous keep-alive still covers the 5--15s click gap.
server.headersTimeout = 15_000;
server.requestTimeout = 30_000;
server.keepAliveTimeout = 30_000;
server.keepAliveTimeoutBuffer = 1_000;
server.maxRequestsPerSocket = 0;

server.listen(Number(process.env.PORT || 80), process.env.HOST || '0.0.0.0');

function shutdown() {
  server.close(() => {
    db.close();
    process.exit(0);
  });
  // A stuck keep-alive must not make a deploy hang forever.
  setTimeout(() => process.exit(0), 5000).unref();
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
