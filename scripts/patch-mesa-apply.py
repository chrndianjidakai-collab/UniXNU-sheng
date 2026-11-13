#!/usr/bin/env python3
"""Allow git apply to create files from patches that use '--- /dev/null'.

The macOS hosted runner's git refuses such a hunk with
    error: dev/null: No such file or directory
unless --unsafe-paths is given. Mesa's turnip patches create new files that
way (tu_knl_darwin.cc and others), so the build stops at the first patch.

This rewrites the single git apply call in scripts/build-boot-runtime.py.
It is idempotent: a second run finds nothing to change.
"""
import pathlib
import sys

TARGET = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
if TARGET is None or not TARGET.is_file():
    print("patch-mesa-apply: no target, nothing to do")
    sys.exit(0)

source = TARGET.read_text(encoding="utf-8")
old = "            run('git', '-C', mesa, 'apply', ROOT / patch)"
new = (
    "            # macOS hosted runners reject '--- /dev/null' creations in\n"
    "            # git apply unless unsafe paths are permitted.\n"
    "            run('git', '-C', mesa, 'apply', '-p1', '--unsafe-paths', ROOT / patch)"
)

if old in source:
    TARGET.write_text(source.replace(old, new), encoding="utf-8")
    print("patch-mesa-apply: rewrote the git apply call")
elif "--unsafe-paths" in source:
    print("patch-mesa-apply: already patched")
else:
    print("patch-mesa-apply: call not found; leaving the file untouched")
