import http from 'node:http';

const sqlitePath = process.env.SQLITE_PATH || 'seed/notes.db';
const host = process.env.HOST || '0.0.0.0';
const port = parseInt(process.env.PORT || '80', 10);

// Initialize SQLite database (prefer better-sqlite3, fallback to node:sqlite)
let dbAdapter;
try {
  const Database = (await import('better-sqlite3')).default;
  const db = new Database(sqlitePath);
  db.pragma('journal_mode = WAL');
  db.pragma('synchronous = NORMAL');
  db.pragma('mmap_size = 536870912');
  db.pragma('cache_size = -16000');
  db.pragma('temp_store = MEMORY');
  db.pragma('busy_timeout = 5000');
  db.pragma('wal_autocheckpoint = 2000');

  const stmtListNotes = db.prepare(`
    SELECT json_object('notes', json_group_array(json_object('id', id, 'author', username, 'body', body, 'created_at', created_at)))
    FROM (
      SELECT n.id as id, u.username as username, n.body as body, n.created_at as created_at
      FROM notes n JOIN users u ON n.user_id = u.id
      ORDER BY n.id DESC LIMIT 20
    )
  `).pluck();

  const stmtGetNote = db.prepare(`
    SELECT json_object('note', json_object('id', n.id, 'author', u.username, 'body', n.body, 'created_at', n.created_at))
    FROM notes n JOIN users u ON n.user_id = u.id WHERE n.id = ?
  `).pluck();

  const stmtGetUserByToken = db.prepare('SELECT id, username FROM users WHERE token = ?').raw();

  const stmtInsertNote = db.prepare(`
    INSERT INTO notes (user_id, body) VALUES (?, ?)
    RETURNING json_object('note', json_object('id', id, 'author', cast(? as text), 'body', body, 'created_at', created_at))
  `).pluck();

  dbAdapter = {
    listNotes: () => stmtListNotes.get(),
    getNote: (id) => stmtGetNote.get(id),
    getUserByToken: (token) => stmtGetUserByToken.get(token),
    insertNote: (userId, body, username) => stmtInsertNote.get(userId, body, username),
  };
} catch (err) {
  const { DatabaseSync } = await import('node:sqlite');
  const db = new DatabaseSync(sqlitePath);
  db.exec('PRAGMA journal_mode = WAL');
  db.exec('PRAGMA synchronous = NORMAL');
  db.exec('PRAGMA mmap_size = 536870912');
  db.exec('PRAGMA cache_size = -16000');
  db.exec('PRAGMA temp_store = MEMORY');
  db.exec('PRAGMA busy_timeout = 5000');
  db.exec('PRAGMA wal_autocheckpoint = 2000');

  const stmtListNotes = db.prepare(`
    SELECT json_object('notes', json_group_array(json_object('id', id, 'author', username, 'body', body, 'created_at', created_at)))
    FROM (
      SELECT n.id as id, u.username as username, n.body as body, n.created_at as created_at
      FROM notes n JOIN users u ON n.user_id = u.id
      ORDER BY n.id DESC LIMIT 20
    )
  `);
  stmtListNotes.setReturnArrays(true);

  const stmtGetNote = db.prepare(`
    SELECT json_object('note', json_object('id', n.id, 'author', u.username, 'body', n.body, 'created_at', n.created_at))
    FROM notes n JOIN users u ON n.user_id = u.id WHERE n.id = ?
  `);
  stmtGetNote.setReturnArrays(true);

  const stmtGetUserByToken = db.prepare('SELECT id, username FROM users WHERE token = ?');
  stmtGetUserByToken.setReturnArrays(true);

  const stmtInsertNote = db.prepare(`
    INSERT INTO notes (user_id, body) VALUES (?, ?)
    RETURNING json_object('note', json_object('id', id, 'author', cast(? as text), 'body', body, 'created_at', created_at))
  `);
  stmtInsertNote.setReturnArrays(true);

  dbAdapter = {
    listNotes: () => stmtListNotes.get()[0],
    getNote: (id) => {
      const row = stmtGetNote.get(id);
      return row ? row[0] : undefined;
    },
    getUserByToken: (token) => stmtGetUserByToken.get(token),
    insertNote: (userId, body, username) => stmtInsertNote.get(userId, body, username)[0],
  };
}

// Pre-computed static responses and headers
const CONTENT_TYPE_JSON = 'application/json';

const RES_HEALTH = Buffer.from('{"status":"ok"}');
const RES_BAD_JSON = Buffer.from('{"error":"bad json"}');
const RES_INVALID_ID = Buffer.from('{"error":"invalid id"}');
const RES_INVALID_BODY = Buffer.from('{"error":"invalid body"}');
const RES_UNAUTHORIZED = Buffer.from('{"error":"unauthorized"}');
const RES_NOT_FOUND = Buffer.from('{"error":"not found"}');

const HEADERS_HEALTH = { 'content-type': CONTENT_TYPE_JSON, 'content-length': RES_HEALTH.length };
const HEADERS_BAD_JSON = { 'content-type': CONTENT_TYPE_JSON, 'content-length': RES_BAD_JSON.length };
const HEADERS_INVALID_ID = { 'content-type': CONTENT_TYPE_JSON, 'content-length': RES_INVALID_ID.length };
const HEADERS_INVALID_BODY = { 'content-type': CONTENT_TYPE_JSON, 'content-length': RES_INVALID_BODY.length };
const HEADERS_UNAUTHORIZED = { 'content-type': CONTENT_TYPE_JSON, 'content-length': RES_UNAUTHORIZED.length };
const HEADERS_NOT_FOUND = { 'content-type': CONTENT_TYPE_JSON, 'content-length': RES_NOT_FOUND.length };

function sendStatic(res, status, buffer, headers) {
  res.writeHead(status, headers);
  res.end(buffer);
}

const server = http.createServer((req, res) => {
  const url = req.url;
  const qIdx = url.indexOf('?');
  const pathname = qIdx === -1 ? url : url.slice(0, qIdx);

  if (req.method === 'GET') {
    if (pathname === '/notes') {
      const json = dbAdapter.listNotes();
      res.writeHead(200, {
        'content-type': CONTENT_TYPE_JSON,
        'content-length': Buffer.byteLength(json),
      });
      res.end(json);
      return;
    }

    if (pathname === '/health') {
      sendStatic(res, 200, RES_HEALTH, HEADERS_HEALTH);
      return;
    }

    if (pathname.startsWith('/notes/')) {
      const idStr = pathname.slice(7);
      if (idStr.length === 0 || idStr.includes('/')) {
        sendStatic(res, 404, RES_NOT_FOUND, HEADERS_NOT_FOUND);
        return;
      }
      if (!/^[1-9]\d*$/.test(idStr) || idStr.length > 15) {
        sendStatic(res, 400, RES_INVALID_ID, HEADERS_INVALID_ID);
        return;
      }
      const id = parseInt(idStr, 10);
      const json = dbAdapter.getNote(id);
      if (!json) {
        sendStatic(res, 404, RES_NOT_FOUND, HEADERS_NOT_FOUND);
        return;
      }
      res.writeHead(200, {
        'content-type': CONTENT_TYPE_JSON,
        'content-length': Buffer.byteLength(json),
      });
      res.end(json);
      return;
    }

    sendStatic(res, 404, RES_NOT_FOUND, HEADERS_NOT_FOUND);
    return;
  }

  if (req.method === 'POST') {
    if (pathname !== '/notes') {
      sendStatic(res, 404, RES_NOT_FOUND, HEADERS_NOT_FOUND);
      return;
    }

    // Auth check first
    const auth = req.headers['authorization'];
    if (!auth || !auth.startsWith('Bearer ')) {
      req.resume();
      sendStatic(res, 401, RES_UNAUTHORIZED, HEADERS_UNAUTHORIZED);
      return;
    }

    const token = auth.slice(7);
    const user = dbAdapter.getUserByToken(token);
    if (!user) {
      req.resume();
      sendStatic(res, 401, RES_UNAUTHORIZED, HEADERS_UNAUTHORIZED);
      return;
    }

    let body = '';
    req.setEncoding('utf8');
    req.on('data', (chunk) => {
      body += chunk;
      if (body.length > 65536) {
        req.destroy();
      }
    });

    req.on('end', () => {
      let parsed;
      try {
        parsed = JSON.parse(body);
      } catch {
        sendStatic(res, 400, RES_BAD_JSON, HEADERS_BAD_JSON);
        return;
      }

      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed) || typeof parsed.body !== 'string') {
        sendStatic(res, 400, RES_INVALID_BODY, HEADERS_INVALID_BODY);
        return;
      }

      const trimmed = parsed.body.trim();
      if (trimmed.length < 1 || trimmed.length > 500) {
        sendStatic(res, 400, RES_INVALID_BODY, HEADERS_INVALID_BODY);
        return;
      }

      const resJson = dbAdapter.insertNote(user[0], trimmed, user[1]);
      res.writeHead(201, {
        'content-type': CONTENT_TYPE_JSON,
        'content-length': Buffer.byteLength(resJson),
      });
      res.end(resJson);
    });
    return;
  }

  sendStatic(res, 404, RES_NOT_FOUND, HEADERS_NOT_FOUND);
});

// Configure keep-alive to support persistent VU connections
server.keepAliveTimeout = 65000;
server.headersTimeout = 66000;
server.requestTimeout = 0;
server.maxHeadersCount = 50;

server.on('connection', (socket) => {
  socket.setNoDelay(true);
});

process.on('uncaughtException', (err) => {
  console.error('Uncaught exception:', err);
});

process.on('unhandledRejection', (err) => {
  console.error('Unhandled rejection:', err);
});

server.listen({ port, host, backlog: 65535 }, () => {
  console.log(`Server listening on ${host}:${port}`);
});
