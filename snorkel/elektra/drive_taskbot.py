#!/usr/bin/env python3
"""Drive taskbot stages on PR #2, one at a time, re-triggering anything that hangs.

usage: drive3.py [--attach] stage [stage ...]
  --attach   the first stage is already running; wait for it instead of posting it

Blocking stages (scope, verify-spec, review) must come back passed or the driver stops.
benchmark and analyze only have to run; the driver stops after the last stage so the
result can be read before /submit.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time

REPO = "deccan-taskbot-private/r065-laravel-php-tasks"
PR = 2
GH = os.path.expanduser("~/.local/bin/gh")
# how long a stage may sit "awaiting result" before it is re-triggered (seconds)
LIMIT = {"scope": 25 * 60, "verify-spec": 30 * 60, "gen-tests": 45 * 60, "review": 100 * 60,
         "benchmark": 5 * 3600, "analyze": 75 * 60, "submit": 20 * 60}
BLOCKING = {"scope", "verify-spec", "review"}
MAX_POSTS = 12


def log(msg):
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}Z] {msg}", flush=True)


def gh(*args):
    for attempt in range(6):
        p = subprocess.run([GH, *args], capture_output=True, text=True)
        if p.returncode == 0:
            return p.stdout
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"gh {' '.join(args)} failed: {p.stderr.strip()}")


def comments():
    return json.loads(gh("api", f"repos/{REPO}/issues/{PR}/comments?per_page=100"))


def status_of(cs):
    for c in cs:
        if "taskbot:status" in c["body"]:
            return c["body"], c["updated_at"]
    return "", ""


def busy(body):
    return "📡" in body or "⏳" in body


def verdict(body, st):
    m = re.search(r"### `/%s` — ([^\n]*)" % re.escape(st), body)
    return m.group(1).strip() if m else None


def post(st):
    gh("pr", "comment", str(PR), "-R", REPO, "--body", f"/{st}")
    time.sleep(3)
    mine = [c for c in comments() if c["body"].strip() == f"/{st}" and not c["user"]["login"].endswith("[bot]")]
    t = mine[-1]["created_at"]
    log(f"posted /{st} (comment at {t})")
    return t


def run_stage(st, attach=False):
    posts = 0
    if attach:
        cs = comments()
        body, upd = status_of(cs)
        t_post = upd
        log(f"attached to running /{st}")
    else:
        t_post = post(st)
        posts += 1
    start = time.time()
    last_post = time.time()
    seen_busy = attach
    while True:
        time.sleep(30)
        cs = comments()
        body, upd = status_of(cs)
        if busy(body) and upd >= t_post:
            seen_busy = True
        refusals = [c for c in cs if c["user"]["login"].endswith("[bot]") and c["created_at"] > t_post
                    and "taskbot:status" not in c["body"] and "refused" in c["body"] and f"`/{st}`" in c["body"]]
        if refusals:
            txt = refusals[-1]["body"]
            if "holds this task" not in txt:
                log(f"/{st} refused for a reason that needs a person:\n{txt}")
                return "refused", txt
            holder = re.search(r"\(`/([\w-]+)`, running for", txt)
            if holder and holder.group(1) == st:
                # the same stage is already running (e.g. auto-started after a push): wait for it
                log(f"/{st} is already running; waiting for that run instead of posting again")
                t_post = refusals[-1]["created_at"]
                seen_busy = True
                start = last_post = time.time()
                continue
            m = re.search(r"running for (\d+)([smh])", txt)
            held = int(m.group(1)) * {"s": 1, "m": 60, "h": 3600}[m.group(2)] if m else 0
            wait = 90 if held < 300 else 600
            log(f"/{st} refused, another job holds the task (running {held}s); retrying in {wait}s")
            time.sleep(wait)
            if posts >= MAX_POSTS:
                return "gave-up", body
            t_post = post(st); posts += 1; start = last_post = time.time(); seen_busy = False
            continue
        v = verdict(body, st)
        if not busy(body) and upd > t_post and (seen_busy or v):
            log(f"/{st} finished: {v}")
            return "done", body
        elapsed = time.time() - start
        if not seen_busy and upd <= t_post and elapsed > 300:
            log(f"/{st} was never picked up after {int(elapsed)}s; posting it again")
        elif seen_busy and elapsed > LIMIT.get(st, 3600) and time.time() - last_post > 600:
            log(f"/{st} has been awaiting a result for {int(elapsed)}s, past its normal time; re-triggering")
        else:
            continue
        if posts >= MAX_POSTS:
            return "gave-up", body
        t_post = post(st); posts += 1; last_post = time.time()
        if not seen_busy:
            start = time.time()


def main():
    args = sys.argv[1:]
    attach = False
    if args and args[0] == "--attach":
        attach = True
        args = args[1:]
    for i, st in enumerate(args):
        res, body = run_stage(st, attach=attach and i == 0)
        print(f"===== /{st}: {res}\n{body}\n", flush=True)
        if res != "done":
            sys.exit(2)
        v = verdict(body, st) or ""
        if st in BLOCKING and "✅" not in v:
            sys.exit(1)
    log("all requested stages finished")


if __name__ == "__main__":
    main()
