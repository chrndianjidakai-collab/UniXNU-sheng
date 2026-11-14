"""Make Ath12kWifi's source lock usable with `git sparse-checkout`.

`tools/fetch-sources.py` calls

    git -C deps/<name> sparse-checkout add <paths...>

with the `paths` array from `tools/source-lock.json` verbatim. That array
cannot be fed to git as-is, for two independent reasons:

1. Every entry carries a leading slash ("/include/"), and git answers
       fatal: specify directories rather than patterns (no leading slash)
2. Several entries name single files, not directories
   ("net/core/skbuff.c", "lib/rbtree.c"), and git answers
       fatal: '<path>' is not a directory; to treat it as a directory anyway,
              rerun with --skip-checks

Both are properties of the repository, not of the machine: a fresh
`python3 tools/fetch-sources.py` cannot finish anywhere.

This script rewrites the lock in place so both problems are gone:

  * leading slashes are stripped
  * entries that name a file are moved out of `paths` into a new
    `files` list, which fetch-sources.py then stages with `git checkout`
    instead of `sparse-checkout add`

The commit pins, the supplicant sha256 and the `required` lists are left
byte-identical.

Usage:
    python fix-ath12k-sparse-paths.py <Ath12kWifi checkout>
"""
import json
import pathlib
import sys

LOCK = 'tools/source-lock.json'


def looks_like_file(path):
    """A trailing slash means directory; a dot in the last segment means file."""
    if path.endswith('/'):
        return False
    last = path.rsplit('/', 1)[-1]
    return '.' in last


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / LOCK
    if not target.is_file():
        raise SystemExit(f'{target} missing')

    lock = json.loads(target.read_text())
    changed = 0

    for name, entry in lock.items():
        if not isinstance(entry, dict):
            continue                      # e.g. "schema": 1
        paths = entry.get('paths')
        if not isinstance(paths, list):
            continue

        dirs, files = [], []
        for raw in paths:
            path = raw.lstrip('/')
            if path != raw:
                changed += 1
            (files if looks_like_file(path) else dirs).append(path)

        if files:
            changed += 1
        entry['paths'] = dirs
        if files:
            # fetch-sources.py stages these with `git checkout <rev> -- <file>`
            entry['files'] = files
        else:
            entry.pop('files', None)

    if not changed:
        print(f'{LOCK}: already normalised, nothing to do')
        return 0

    target.write_text(json.dumps(lock, indent=2) + '\n')
    print(f'{LOCK}: normalised')
    for name, entry in lock.items():
        if not isinstance(entry, dict) or 'paths' not in entry:
            continue
        print(f'  {name}.paths: {entry["paths"]}')
        if entry.get('files'):
            print(f'  {name}.files: {entry["files"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
