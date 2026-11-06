#!/usr/bin/env python3
"""V7: one agent, one prompt, one Node backend. Runs the agent in its own folder (a copy-on-write clone of v7-sablon).
Claude and Gemini run inside a macOS sandbox profile that hides ~/Developer (the measurement code and the hidden test),
the other runs and the keys. Codex has its own sandbox and cannot run inside another one: its transcript is checked
afterwards for reads outside its folder.
  python3 kos.py claude|codex|gemini <run-name> [--minutes 60]
Writes ~/deney-v7/<run-name>/ and copies it, without node_modules and the seed, to runs/<run-name>/."""
import json, os, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
H = Path.home()
agent, run_name = sys.argv[1], sys.argv[2]
minutes = int(sys.argv[sys.argv.index("--minutes") + 1]) if "--minutes" in sys.argv else 60
prompt = (HERE / "PROMPT.txt").read_text().strip()
run = H / "deney-v7" / run_name      # not under a dot folder: Claude Code treats those as sensitive and refuses to write
shutil.rmtree(run, ignore_errors=True)
run.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(["cp", "-cR", str(H / ".cache/deney-runs/v7-sablon"), str(run)], check=True)   # APFS clone: instant, no extra disk
(run / ".tmp").mkdir()
MODELS = {"claude": os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"), "codex": "gpt-5.6-terra", "gemini": "gemini-3.8-flash-high"}
# Hide every other run by name. Denying the parent folder instead makes Claude Code call every file in the run "sensitive"
# and refuse to write it: it checks the parent and gets "operation not permitted".
NAMES = [f"{a}-{i}" for a in ("claude", "codex", "gemini") for i in range(1, 6)] + [f"t-{c}" for c in "abc"]
def profile(name):
    others = "\n".join(f'  (subpath "{H}/deney-v7/{n}")' for n in NAMES if n != run_name)
    path = run / ".tmp" / name
    path.write_text((HERE / name).read_text().replace("  ;KARDESLER", others))
    return str(path)
SB = ["sandbox-exec", "-D", f"RUN={run}", "-f", profile("kutu.sb")]
SB_GEMINI = ["sandbox-exec", "-D", f"RUN={run}", "-f", profile("kutu-siki.sb")]
CLAUDE = sorted(H.glob(".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"),
                key=lambda p: [int(x) for x in p.parts[-4].split("-")[2].split(".")])[-1]
TOOLS = "Read Write Edit Glob Grep " + " ".join(f"Bash({c}:*)" for c in
        ["node", "npm", "npx", "python3", "bash", "sh", "ls", "cat", "cp", "mv", "rm", "mkdir", "diff", "wc", "head", "tail", "grep",
         "sed", "awk", "sort", "kill", "pkill", "ps", "lsof", "sleep", "time", "echo", "printf", "chmod", "touch", "which", "pwd", "test", "sqlite3"])
AGY = json.dumps({"permissions": {"allow": [f"write_file({run})", f"read_file({run})", "command(*)"]}})
CMD = {
    "claude": [*SB, str(CLAUDE), "-p", prompt, "--model", MODELS["claude"], "--permission-mode", "acceptEdits",
               "--allowedTools", TOOLS, "--output-format", "stream-json", "--verbose"],
    # network_access lets Codex reach its own server on localhost, like the other two; the prompt says there is no internet
    "codex": ["codex", "exec", "-m", MODELS["codex"], "-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true",
              "--skip-git-repo-check", "-c", "mcp_servers={}", "--color", "never", "--json", "-o", "codex-last.md", prompt],
    "gemini": [*SB_GEMINI, str(H / ".local/bin/agy"), "--print", prompt, "--model", MODELS["gemini"], "--settings", AGY,
               "--print-timeout", f"{minutes}m", "--output-format", "stream-json", "--disable-slash-commands"],
}[agent]
env = dict(os.environ, PWD=str(run), OLDPWD=str(run), CI="1", TERM="dumb", NO_COLOR="1", TMPDIR=str(run / ".tmp"),
           npm_config_cache=str(run / ".tmp/npm"), npm_config_offline="true",
           PATH=f"{H}/.cache/deney-runs/v7-bin:" + os.environ["PATH"])
t0 = time.time(); timed_out = False
with open(run / "transcript.jsonl", "w") as log:
    try:
        code = subprocess.run(CMD, cwd=run, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                              timeout=minutes * 60, text=True).returncode
    except subprocess.TimeoutExpired:
        timed_out, code = True, -1
subprocess.run(["pkill", "-f", f"{run}/"], check=False)        # servers the agent left running
meta = {"agent": agent, "model": MODELS[agent], "run": run_name, "seconds": round(time.time() - t0), "exit_code": code,
        "timed_out": timed_out, "started": time.strftime("%Y-%m-%d %H:%M", time.localtime(t0))}
(run / "meta.json").write_text(json.dumps(meta, indent=1))
print(json.dumps(meta), flush=True)
keep = HERE / "runs" / run_name
shutil.rmtree(keep, ignore_errors=True)
shutil.copytree(run, keep, ignore=shutil.ignore_patterns("node_modules", "seed", ".tmp", "*.db", "*.db-wal", "*.db-shm", "__pycache__", "SPEC.md", "test_api.py", "yuk.js"))
