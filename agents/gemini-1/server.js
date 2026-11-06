'use strict';

const http = require('node:http');
const Database = require('better-sqlite3');

const SQLITE_PATH = process.env.SQLITE_PATH || 'seed/notes.db';
const HOST = process.env.HOST || '0.0.0.0';
const PORT = parseInt(process.env.PORT || '80', 10);

const db = new Database(SQLITE_PATH, { fileMustExist: true });

// Configure SQLite for high performance and durability under WAL mode
db.pragma('journal_mode = WAL');
db.pragma('synchronous = NORMAL');
db.pragma('mmap_size = 335544320'); // 320 MB mmap
db.pragma('cache_size = -32000');   // 32 MB page cache
db.pragma('temp_store = MEMORY');
db.pragma('busy_timeout = 5000');
db.pragma('wal_autocheckpoint = 1000');

// Prepared statements returning pre-formatted JSON directly from SQLite
const stmtList = db.prepare(
  "SELECT json_object('notes', json_group_array(json_object('id', id, 'author', author, 'body', body, 'created_at', created_at))) " +
  "FROM (" +
  "  SELECT notes.id, users.username AS author, notes.body, notes.created_at " +
  "  FROM notes JOIN users ON notes.user_id = users.id " +
  "  ORDER BY notes.id DESC LIMIT 20" +
  ")"
);

const stmtGet = db.prepare(
  "SELECT json_object('note', json_object('id', notes.id, 'author', users.username, 'body', notes.body, 'created_at', notes.created_at)) " +
  "FROM notes JOIN users ON notes.user_id = users.id " +
  "WHERE notes.id = ?"
);

const stmtUserByToken = db.prepare(
  'SELECT id, username FROM users WHERE token = ?'
);

const stmtInsertNote = db.prepare(
  "INSERT INTO notes (user_id, body) VALUES (?, ?) " +
  "RETURNING json_object('note', json_object('id', id, 'author', ?, 'body', body, 'created_at', created_at))"
);

// Pre-encoded static responses
const RESP_HEALTH = Buffer.from('{"status":"ok"}');
const RESP_ERR_NOT_FOUND = Buffer.from('{"error":"not found"}');
const RESP_ERR_UNAUTHORIZED = Buffer.from('{"error":"unauthorized"}');
const RESP_ERR_INVALID_ID = Buffer.from('{"error":"invalid id"}');
const RESP_ERR_BAD_JSON = Buffer.from('{"error":"bad json"}');
const RESP_ERR_INVALID_BODY = Buffer.from('{"error":"invalid body"}');

// Helper to check positive integer: starts with 1-9 followed by digits only
const POS_INT_RE = /^[1-9]\d*$/;

const server = http.createServer({
  keepAlive: true,
  keepAliveInitialDelay: 0,
}, (req, res) => {
  const method = req.method;
  let url = req.url;

  // Strip query string if present
  const qIdx = url.indexOf('?');
  if (qIdx !== -1) {
    url = url.slice(0, qIdx);
  }

  if (method === 'GET') {
    if (url === '/notes') {
      const payload = stmtList.pluck().get() || '{"notes":[]}';
      res.writeHead(200, {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload)
      });
      res.end(payload);
      return;
    }

    if (url === '/health') {
      res.writeHead(200, {
        'Content-Type': 'application/json',
        'Content-Length': RESP_HEALTH.length
      });
      res.end(RESP_HEALTH);
      return;
    }

    if (url.startsWith('/notes/')) {
      const idStr = url.slice(7);
      if (!POS_INT_RE.test(idStr) || idStr.length > 15) {
        res.writeHead(400, {
          'Content-Type': 'application/json',
          'Content-Length': RESP_ERR_INVALID_ID.length
        });
        res.end(RESP_ERR_INVALID_ID);
        return;
      }

      const id = parseInt(idStr, 10);
      const payload = stmtGet.pluck().get(id);
      if (!payload) {
        res.writeHead(404, {
          'Content-Type': 'application/json',
          'Content-Length': RESP_ERR_NOT_FOUND.length
        });
        res.end(RESP_ERR_NOT_FOUND);
        return;
      }

      res.writeHead(200, {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload)
      });
      res.end(payload);
      return;
    }

    // Any other GET
    res.writeHead(404, {
      'Content-Type': 'application/json',
      'Content-Length': RESP_ERR_NOT_FOUND.length
    });
    res.end(RESP_ERR_NOT_FOUND);
    return;
  }

  if (method === 'POST') {
    if (url === '/notes') {
      // 1. Authorization checked first
      const auth = req.headers['authorization'];
      if (!auth || !auth.startsWith('Bearer ')) {
        res.writeHead(401, {
          'Content-Type': 'application/json',
          'Content-Length': RESP_ERR_UNAUTHORIZED.length
        });
        res.end(RESP_ERR_UNAUTHORIZED);
        return;
      }

      const token = auth.slice(7);
      const user = stmtUserByToken.get(token);
      if (!user) {
        res.writeHead(401, {
          'Content-Type': 'application/json',
          'Content-Length': RESP_ERR_UNAUTHORIZED.length
        });
        res.end(RESP_ERR_UNAUTHORIZED);
        return;
      }

      // 2. Read body
      let chunks = '';
      req.setEncoding('utf8');
      req.on('data', chunk => {
        chunks += chunk;
        if (chunks.length > 65536) {
          req.destroy();
        }
      });

      req.on('end', () => {
        let parsed;
        try {
          parsed = JSON.parse(chunks);
        } catch {
          res.writeHead(400, {
            'Content-Type': 'application/json',
            'Content-Length': RESP_ERR_BAD_JSON.length
          });
          res.end(RESP_ERR_BAD_JSON);
          return;
        }

        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || typeof parsed.body !== 'string') {
          res.writeHead(400, {
            'Content-Type': 'application/json',
            'Content-Length': RESP_ERR_INVALID_BODY.length
          });
          res.end(RESP_ERR_INVALID_BODY);
          return;
        }

        const trimmed = parsed.body.trim();
        if (trimmed.length < 1 || trimmed.length > 500) {
          res.writeHead(400, {
            'Content-Type': 'application/json',
            'Content-Length': RESP_ERR_INVALID_BODY.length
          });
          res.end(RESP_ERR_INVALID_BODY);
          return;
        }

        const payload = stmtInsertNote.pluck().get(user.id, trimmed, user.username);
        res.writeHead(201, {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(payload)
        });
        res.end(payload);
      });
      return;
    }

    res.writeHead(404, {
      'Content-Type': 'application/json',
      'Content-Length': RESP_ERR_NOT_FOUND.length
    });
    res.end(RESP_ERR_NOT_FOUND);
    return;
  }

  // Any other method
  res.writeHead(404, {
    'Content-Type': 'application/json',
    'Content-Length': RESP_ERR_NOT_FOUND.length
  });
  res.end(RESP_ERR_NOT_FOUND);
});

// Configure timeouts and keep-alive
server.keepAliveTimeout = 75000;
server.headersTimeout = 80000;

server.on('connection', socket => {
  socket.setNoDelay(true);
});

server.listen(PORT, HOST, 65535, () => {
  console.log(`Server listening on ${HOST}:${PORT}`);
});
