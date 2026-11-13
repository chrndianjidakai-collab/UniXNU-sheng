#!/usr/bin/env python3
"""Make Mesa patch application work on the macOS hosted runner.

The runner's git refuses patches that create files through '--- /dev/null':
    error: dev/null: No such file or directory
Mesa's turnip patches create several files that way, and later patches modify
those files, so the build stops at the first one.

This rewrites the git apply call in scripts/build-boot-runtime.py to use
patch(1), which handles /dev/null hunk headers correctly, then commits the
result so the next patch sees a clean tree.

It is idempotent: a second run finds the replacement already present.
"""
import pathlib
import sys

TARGET = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
if TARGET is None or not TARGET.is_file():
    print("build boot runtime not found; nothing to do")
    sys.exit(0)

source = TARGET.read_text(encoding="utf-8")

OLD = "            run('git', '-C', mesa, 'apply', ROOT / patch)"
NEW = (
    "            # macOS hosted runners: git apply refuses '--- /dev/null'\n"
    "            # file creations, which several Mesa patches use. patch(1)\n"
    "            # creates them correctly; commit so the next patch applies\n"
    "            # against the updated tree.\n"
    "            run('patch', '-p1', '--fuzz=3', '-d', str(mesa), '-i', str(ROOT / patch), '--forward', '--batch')\n"
    "            run('git', '-C', mesa, 'add', '-A')\n"
    "            run('git', '-C', mesa, 'commit', '-q', '-m', 'patch ' + str(patch))"
)

if NEW.splitlines()[4] in source:
    print("already rewritten")
    sys.exit(0)

if OLD not in source:
    print("git apply call not found; leaving the file untouched")
    sys.exit(1)

TARGET.write_text(source.replace(OLD, NEW), encoding="utf-8")
print("rewrote the Mesa patch loop to use patch(1)")
