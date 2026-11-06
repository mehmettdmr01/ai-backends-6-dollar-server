'use strict';
// The baseline: the notes API written the way a tutorial would write it. One process, default settings, no tuning.
const express = require('express');
const Database = require('better-sqlite3');

const db = new Database(process.env.SQLITE_PATH);
const NOTE = `SELECT n.id, u.username AS author, n.body, n.created_at FROM notes n JOIN users u ON u.id = n.user_id`;
const list = db.prepare(`${NOTE} ORDER BY n.id DESC LIMIT 20`);
const one = db.prepare(`${NOTE} WHERE n.id = ?`);
const who = db.prepare('SELECT id, username FROM users WHERE token = ?');
const insert = db.prepare('INSERT INTO notes (user_id, body) VALUES (?, ?) RETURNING id, created_at');

const app = express();
app.disable('x-powered-by');

function auth(req, res, next) {
  const header = req.get('authorization') || '';
  const user = header.startsWith('Bearer ') ? who.get(header.slice(7)) : undefined;
  if (!user) return res.status(401).json({ error: 'unauthorized' });
  req.user = user;
  next();
}

app.get('/health', (req, res) => res.json({ status: 'ok' }));
app.get('/notes', (req, res) => res.json({ notes: list.all() }));

app.get('/notes/:id', (req, res) => {
  if (!/^[1-9]\d*$/.test(req.params.id)) return res.status(400).json({ error: 'invalid id' });
  const note = one.get(Number(req.params.id));
  if (!note) return res.status(404).json({ error: 'not found' });
  res.json({ note });
});

app.post('/notes', auth, express.json({ strict: false }), (req, res) => {
  const raw = req.body && req.body.body;
  const body = typeof raw === 'string' ? raw.trim() : '';
  if (!body || body.length > 500) return res.status(400).json({ error: 'invalid body' });
  const row = insert.get(req.user.id, body);
  res.status(201).json({ note: { id: row.id, author: req.user.username, body, created_at: row.created_at } });
});

app.use((req, res) => res.status(404).json({ error: 'not found' }));
app.use((err, req, res, next) => {
  if (err.type === 'entity.parse.failed') return res.status(400).json({ error: 'bad json' });
  res.status(500).json({ error: 'internal server error' });
});

app.listen(Number(process.env.PORT), process.env.HOST);
