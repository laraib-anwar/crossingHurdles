"""Deterministic submission ZIP of the task (dev tool, not shipped).

Includes exactly the six root entries (instruction.md, task.toml, README.md, environment/,
solution/, tests/), sorted, with fixed timestamps, after scanning for stray files, canary
strings, secrets, bytecode and disallowed extensions under tests/. Writes the ZIP and a
SHA256 manifest next to it.

usage: build_zip.py <task_dir> <out_dir>
"""
import hashlib
import re
import sys
import zipfile
from pathlib import Path

task = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
ROOT_ENTRIES = {"instruction.md", "task.toml", "README.md", "environment", "solution", "tests"}
TESTS_EXT = {".py", ".sh", ".r", ".jl", ".c", ".h", ".cpp", ".hpp", ".f", ".f90", ".m", ".csv", ".tsv", ".json",
             ".jsonl", ".ndjson", ".npy", ".npz", ".parquet", ".parq", ".h5", ".hdf5", ".fits", ".pkl", ".txt",
             ".dat", ".nc", ".mat", ".xyz", ".pdb", ".cif", ".fasta", ".fa", ".fastq", ".vcf", ".sdf", ".mol2", ".gz"}
BAD_PATTERNS = [re.compile(p, re.I) for p in (r"canary", r"BENCHMARK DATA SHOULD NEVER", r"api[_-]?key\s*[=:]",
                                                 r"sk-[A-Za-z0-9]{20,}", r"-----BEGIN [A-Z ]*PRIVATE KEY")]

problems = []
entries = sorted(p.name for p in task.iterdir())
if set(entries) != ROOT_ENTRIES:
    problems.append(f"root entries are {entries}, expected {sorted(ROOT_ENTRIES)}")
files = sorted(p for p in task.rglob("*") if p.is_file())
for p in files:
    rel = p.relative_to(task)
    if "__pycache__" in rel.parts or p.suffix == ".pyc" or p.name == ".DS_Store":
        problems.append(f"stray file {rel}")
    if rel.parts[0] == "tests" and p.name != "Dockerfile" and p.suffix not in TESTS_EXT:
        problems.append(f"disallowed extension under tests/: {rel}")
    if p.name.startswith(".") and rel.parts[0] == "tests":
        problems.append(f"dotfile under tests/: {rel}")
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        problems.append(f"not UTF-8: {rel}")
        continue
    for pat in BAD_PATTERNS:
        if pat.search(text):
            problems.append(f"pattern {pat.pattern!r} in {rel}")
if problems:
    print("NOT BUILT:")
    for q in problems:
        print("  -", q)
    sys.exit(1)
zpath = out / f"{task.name}.zip"
with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for p in files:
        rel = p.relative_to(task).as_posix()
        info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (0o755 if p.suffix == ".sh" else 0o644) << 16
        zf.writestr(info, p.read_bytes())
digest = hashlib.sha256(zpath.read_bytes()).hexdigest()
version = re.search(r'^version\s*=\s*"([^"]+)"', (task / "task.toml").read_text(), re.M).group(1)
(out / "SHA256SUMS.txt").write_text(f"{digest}  {zpath.name}  (task version {version})\n")
print(f"built {zpath} ({zpath.stat().st_size} bytes, {len(files)} files), version {version}\nsha256 {digest}")
