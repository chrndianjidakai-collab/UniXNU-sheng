#!/usr/bin/env python3
"""Repair the Mesa patch series in a UniXNU checkout before it is applied.

Only one defect is fixed here, and it is a header-format defect, not a content
change:

  patches/mesa/turnip-frame-diagnostics.patch creates
  src/freedreno/vulkan/tu_frame_diagnostic.h, but its diff header is missing the
  "new file mode" and "index" lines that git requires to recognise a created
  file. git then reads "/dev/null" as a literal path and aborts with

      error: dev/null: No such file or directory

  The two other file-creating patches in the series (turnip-darwin-kmd.patch,
  turnip-builtin-shader-pack.patch) do carry those lines, which is why only this
  one breaks. The hunk body is untouched, so the patched tree still
  reconstructs the pinned Mesa commit byte for byte.

Usage: repair-mesa-series.py <UniXNU checkout>
"""
import sys
from pathlib import Path

PATCH = 'patches/mesa/turnip-frame-diagnostics.patch'


def repair(path):
    lines = path.read_text().split('\n')
    if any(l.startswith('new file mode') for l in lines):
        return False

    out = []
    inserted = 0
    for line in lines:
        if line.startswith('--- /dev/null'):
            # locate the "diff --git" line this header belongs to
            for j in range(len(out) - 1, -1, -1):
                if out[j].startswith('diff --git '):
                    break
            else:
                j = None
            if j is not None and not any(l.startswith('new file mode')
                                         for l in out[j:]):
                out.append('new file mode 100644')
                out.append('index 0000000..0000000')
                inserted += 1
        out.append(line)

    if not inserted:
        raise SystemExit(f'{path}: /dev/null hunk found but no diff --git header')

    path.write_text('\n'.join(out))
    return True


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / PATCH
    if not target.is_file():
        print(f'repair: {PATCH} not present, nothing to do')
        return 0
    if repair(target):
        print(f'repair: added the missing new-file header to {PATCH}')
    else:
        print(f'repair: {PATCH} already carries a new-file header')
    return 0


if __name__ == '__main__':
    sys.exit(main())
