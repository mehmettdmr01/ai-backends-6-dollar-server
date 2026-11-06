# Which AI can handle the most users on a $6 server?

Video: (link coming)

I gave three AI coding agents the same prompt ([PROMPT.txt](PROMPT.txt)): write a small notes API in Node.js
(list the latest 20 notes, open one note, save a new note; SQLite with 20,000 users and 1,000,000 notes) and make it carry
as many users as possible on a DigitalOcean **$6/month server (1 vCPU, 1 GB RAM)**. Each agent ran once, 45 minutes max,
no internet, shut inside its own folder, with the ordinary model my subscription gives it: **Codex (GPT-5.6 Terra),
Claude Code (Sonnet 5.5), Gemini CLI (Gemini 3.8 Flash)**. As a baseline I wrote the kind of Express app you see in
tutorials and didn't touch any of its settings. Then I sent simulated users at each one until it broke, on two days,
on two different $6 servers.

## Results

A user clicks once every 5-15 seconds (70% list, 20% one note, 10% new note), so 10 users ≈ 1 request/second.
**Score = the most users held for 5 minutes with p95 under 1 s and under 1% errors** (and the process still alive).
Each run: a 10-minute ramp from zero to find where it breaks, then 5-minute holds just below that.

| | Round 1 (5 Nov) | Round 2 (6 Nov) | Round 2 broke at | How it broke | Round 2 p95 at the score | Round 2 req/s |
|---|---|---|---|---|---|---|
| **Codex** | ≥ 22,500 * | **26,200** | 29,166 | errors (CPU) | 132 ms | 2,333 |
| **Claude** | 18,000 | **22,500** | 25,000 | errors (CPU) | 279 ms | 2,005 |
| **Gemini** | 19,500 | **21,000** | 23,333 | out of memory, the OS killed the process | 81 ms | 1,874 |
| **Express baseline** | 12,400 | **16,500** | 18,333 | p95 over 1 s | 554 ms | 1,435 |

\* Round 1 used one 8 GB load generator, which tops out around 25,000 users; Codex never broke. Round 2 used two.

- All four passed the 28 API checks and the hidden test in both rounds. The hidden test ([measure/gizli_test.py](measure/gizli_test.py))
  changes rows and tokens behind the server's back (catches caching the answers) and `kill -9`s the server while writers are
  running, then checks that every note that got a 201 is in the database.
- **Codex first and Express last in both rounds. Claude and Gemini are a tie:** each was ahead in one round. The $6 box is a
  shared vCPU; during Claude's round-1 hold the neighbours took 21% of the CPU (steal), against 6.5% in round 2.
  The same Express code scored 12,400 and 16,500: that is the size of the noise.
- **Keep-alive.** Node keeps an idle connection open for 5 s by default; these users click every 5-15 s, so with Express
  almost every click opens a new connection. Under load the kernel logged
  `TCP: request_sock_TCP: Possible SYN flooding on port 0.0.0.0:80. Sending cookies.` All three agents raised the timeout
  (Claude 120 s, Gemini 75 s, Codex 65 s), dropped Express for `node:http`, and stayed in one process.
  **I did not measure Express with a longer keep-alive**, so how much of the gap this explains is not known.
- **Writing time:** Claude 89 s, Codex 454 s, Gemini 968 s. Only Gemini load-tested its own code (on my Mac: 300 connections,
  19,216 requests/s; on the server it carried ~1,874 requests/s with 20,000+ connections open).

## My mistakes, and the disk

- **Ubuntu's own update spoiled one run.** Gemini's first round-2 run scored 12,700. The server's journal showed
  `apt-daily-upgrade.service: Consumed 3min 22.628s CPU time, 694.7M memory peak` during the test, on a 1 GB box.
  I discarded that run ([results/round-2-spoiled-by-ubuntu-update](results/round-2-spoiled-by-ubuntu-update)), disabled the
  timers in [measure/uzak/kur-hedef.sh](measure/uzak/kur-hedef.sh) and re-ran it: 21,000. It may have hit round 1 too;
  that server was already deleted, so I can't check.
- **Same price, different disks.** Every new note waits for an fsync. sysbench fsync/s on the five $6 servers I measured:
  3,270 · 2,851 · 1,184 · 920 · 316. Round 1 ran on the 2,851 box, round 2 on the 3,270 one; the slow ones were rejected.
- **Second tries.** I gave each agent the prompt a second time ([agents/*-2](agents)). Claude's second try switched from
  `node:sqlite` to `better-sqlite3` and had not broken at 25,000 on the ramp when I stopped; it has no score. Codex's and
  Gemini's second tries were not measured.

## Files

| Path | What it is |
|---|---|
| `PROMPT.txt` | the prompt every agent got |
| `agents/<agent>-1/` | the measured code, the agent's own `NOTES.md`, build/start scripts (`meta.json`: model, seconds) |
| `agents/<agent>-2/` | second tries, not scored |
| `agents/runner/` | `kos.py` (runs one agent unattended) and the macOS sandbox profiles (`kutu*.sb`) |
| `express-baseline/` | the tutorial-style Express app |
| `load-test/yuk.js` | the k6 user model (one click every 5-15 s); `prob.py` is a one-request-per-second latency probe |
| `measure/SPEC.md` | the API the agents had to implement |
| `measure/seed.py` | the deterministic 20,000-user, 1,000,000-note database |
| `measure/test_api.py`, `measure/gizli_test.py` | the 28 API checks and the hidden test |
| `measure/arama.py` | the search: ramp, find the knee, 5-minute holds; writes `kosular.json` and `sonuc.json` |
| `measure/dagit.sh`, `measure/uzak/` | copy everything to the rented boxes; set up target and load generator; per-second box sampler (`izle.py`) |
| `measure/do_kutu.py` | create/list/delete the DigitalOcean droplets (token from `DO_TOKEN`) |
| `results/round-1/`, `results/round-2/` | per contestant: `kosular.json` (every ramp and hold), `sonuc.json`, per-second box CSVs, probe CSVs, test output; `box.txt` = the server's CPU and disk numbers |
| `results/OZET-tr.md` | my running notes in Turkish |

Some file names and comments are Turkish (yük = load, arama = search, gizli = hidden, sonuç = result, kutu = box).

## Limits

One task, one server type, one scored try per agent, and none of them ran its top model. Two rounds on a shared vCPU
are not enough to separate Claude from Gemini. Models change every month.

The idea comes from Arjay McCandless's $12 server videos (for example
[Which Programming Language Can Handle the Most Users on a $12 Server?](https://youtu.be/sQXFhh_PiG4)) and his open
[$12 Server Challenge](https://github.com/arjaythedev/twelve-dollar-server-challenge). This test (API, user model, score)
is my own, so the numbers are not comparable to his.

I make this channel with Claude Code's help, and the narration is a synthesized voice. The measurements are real; every file
is here to check. Total server cost of the experiment: about $1.29.
