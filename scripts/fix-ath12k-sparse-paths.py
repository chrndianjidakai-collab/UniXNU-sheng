"""Normalise the sparse-checkout paths in Ath12kWifi's source lock.

`tools/source-lock.json` lists every sparse path with a leading slash:

    "paths": ["/drivers/net/wireless/ath/", "/include/", "/lib/rbtree.c", ...]

`tools/fetch-sources.py` passes them straight to

    git -C deps/<name> sparse-checkout add <paths...>

and git refuses them:

    fatal: specify directories rather than patterns (no leading slash)

so a fresh `python3 tools/fetch-sources.py` cannot finish on any machine. The
repository is checked out read-only in CI, so the lock file is rewritten in
place before the fetch runs.

Only the `paths` arrays are touched; every other field (commit pins, sha256,
required files) is left byte-identical.

Usage:
    python fix-ath12k-sparse-paths.py <Ath12kWifi checkout>
"""
import json
import pathlib
import sys

LOCK = 'tools/source-lock.json'


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / LOCK
    if not target.is_file():
        raise SystemExit(f'{target} missing')

    lock = json.loads(target.read_text())
    changed = 0
    for name, entry in lock.items():
        if not isinstance(entry, dict):
            continue          # e.g. "schema": 1
        paths = entry.get('paths')
        if not isinstance(paths, list):
            continue
        fixed = []
        for path in paths:
            stripped = path.lstrip('/')
            if stripped != path:
                changed += 1
            fixed.append(stripped)
        entry['paths'] = fixed

    if not changed:
        print(f'{LOCK}: no leading-slash paths found, nothing to do')
        return 0

    target.write_text(json.dumps(lock, indent=2) + '\n')
    print(f'{LOCK}: stripped the leading slash from {changed} sparse path(s)')

    # show what changed for the log
    for name, entry in lock.items():
        if isinstance(entry, dict) and isinstance(entry.get('paths'), list):
            print(f'  {name}: {entry["paths"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
