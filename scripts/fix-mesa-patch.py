#!/usr/bin/env python3
"""Apply the pinned Mesa patch series on the macOS hosted runner.

Two problems appear there and not on a developer Mac:

1. git apply refuses a hunk whose old side is '--- /dev/null' with
     error: dev/null: No such file or directory
   Only three of the pinned patches create files that way, so the flag is
   needed for those alone. Applying it to the whole series made git skip the
   file creation bookkeeping and later patches could not find the files.

2. scripts/mesa_patch_identity.py proves the applied series reconstructs the
   pinned commit: it reverse-applies every patch in a scratch tree and compares
   each touched file byte for byte with git HEAD. That check only passes when
   every patch applied exactly, so fuzzy matching must not be used.

This rewrites the loop in scripts/build-boot-runtime.py to run git apply with
--unsafe-paths only for patches that create files, keeping the tree exact.
"""
import pathlib
import sys

TARGET = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
if TARGET is None or not TARGET.is_file():
    print("build-boot-runtime.py not found")
    sys.exit(0)

source = TARGET.read_text(encoding="utf-8")

OLD = "            run('git', '-C', mesa, 'apply', ROOT / patch)"
NEW = (
    "            # A patch whose old side is '/dev/null' creates a file; the\n"
    "            # hosted runner's git needs --unsafe-paths for that form, but\n"
    "            # the flag must not touch patches that edit existing files:\n"
    "            # mesa_patch_identity.py reverse-applies the series and\n"
    "            # compares every file with the pinned commit byte for byte.\n"
    "            text = (ROOT / patch).read_text()\n"
    "            create = '\\n--- /dev/null' in text\n"
    "            argv = ['git', '-C', mesa, 'apply']\n"
    "            if create:\n"
    "                argv.append('--unsafe-paths')\n"
    "            argv.append(ROOT / patch)\n"
    "            run(*argv)"
)

MARKER = "create = '\\n--- /dev/null' in text"

if MARKER in source:
    print("already rewritten")
    sys.exit(0)

if OLD not in source:
    print("git apply call not found")
    sys.exit(1)

TARGET.write_text(source.replace(OLD, NEW), encoding="utf-8")
print("rewrote the Mesa patch loop: unsafe-paths only for file-creating patches")
