#!/usr/bin/env python3
"""Unpack and repack the new-file sections of a task's tests/test.patch.

  testpatch.py extract tasks/<slug>/tests/test.patch <dir>
      writes every file the patch creates into <dir>, at its repo-relative path
  testpatch.py pack tasks/<slug>/tests/test.patch <dir>
      for every new-file section whose file exists in <dir>, swaps in that file's content and
      recomputes the "@@ -0,0 +1,N @@" count and the "index 0000000..<blob>" hash

Edit the extracted files, then pack. Sections that modify existing files (composer.json and the
like) are left alone. After packing, add new test ids to tests/config.json and run the verifier
locally (verify_local.sh).
"""
import os
import re
import subprocess
import sys


def sections(text):
    starts = [m.start() for m in re.finditer(r"(?m)^diff --git ", text)]
    for i, s in enumerate(starts):
        yield s, (starts[i + 1] if i + 1 < len(starts) else len(text))


def blob(content):
    return subprocess.run(["git", "hash-object", "--stdin"], input=content.encode(),
                          capture_output=True, check=True).stdout.decode().strip()


def parse_new(sec):
    m = re.search(r"@@ -0,0 \+1,(\d+) @@\n", sec)
    if "new file mode" not in sec or not m:
        return None
    path = sec.split("\n", 1)[0].split(" b/", 1)[1]
    body = sec[m.end():]
    noeol = "\n\\ No newline at end of file" in body
    lines = [l[1:] for l in body.split("\n") if l.startswith("+")]
    return path, m, "\n".join(lines) + ("" if noeol else "\n")


def extract(patch, out):
    text = open(patch).read()
    for s, e in sections(text):
        p = parse_new(text[s:e])
        if p:
            path, _, content = p
            dest = os.path.join(out, path)
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            open(dest, "w").write(content)
            print("extracted", path)


def pack(patch, src):
    text = open(patch).read()
    out, last = [], 0
    for s, e in sections(text):
        sec = text[s:e]
        p = parse_new(sec)
        if p and os.path.exists(os.path.join(src, p[0])):
            path, m, old = p
            new = open(os.path.join(src, path)).read()
            if new != old:
                lines = new[:-1].split("\n") if new.endswith("\n") else new.split("\n")
                head = sec[:m.end()]
                idx = re.search(r"index 0000000\.\.([0-9a-f]+)", head)
                if idx:  # some sections carry no index line (patch applies them fine without one)
                    head = head.replace(idx.group(0), "index 0000000.." + blob(new)[:len(idx.group(1))])
                head = head.replace(m.group(0), "@@ -0,0 +1,%d @@\n" % len(lines))
                body = "\n".join("+" + l for l in lines) + ("\n" if new.endswith("\n") else "\n\\ No newline at end of file\n")
                sec = head + body
                print("packed", path, len(lines), "lines")
        out.append(text[last:s] + sec)
        last = e
    out.append(text[last:])
    open(patch, "w").write("".join(out))


if __name__ == "__main__":
    cmd, patch, d = sys.argv[1:4]
    {"extract": extract, "pack": pack}[cmd](patch, d)
