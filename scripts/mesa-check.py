#!/usr/bin/env python3
"""Validate the pinned Mesa patch series against its pinned commit.

Replaces the previous --unsafe-paths workaround. That flag was only ever needed
because one patch in the series had a malformed file-creation header; with the
header repaired (scripts/repair-mesa-series.py) plain `git apply` accepts all 17
patches, so the series stays byte-exact and the reverse-apply identity check can
pass.

The work is split out of build-boot-runtime.py so this stage can run on any
platform with git and python3 -- it never calls hdiutil, codesign or Xcode.
"""
import json
import pathlib
import subprocess
import sys


def run(*argv, **kw):
    return subprocess.run([str(a) for a in argv], capture_output=True, **kw)


def checkout(path, pin):
    """Fetch the pinned commit into `path`; return True when it was created."""
    if not path.exists():
        path.mkdir(parents=True)
        run('git', 'init', '-q', path, check=True)
        run('git', '-C', path, 'fetch', '--depth=1',
            pin.get('mirror', pin['repository']), pin['commit'], check=True)
        run('git', '-C', path, 'checkout', '--detach', 'FETCH_HEAD', check=True)
        return True
    head = run('git', '-C', path, 'rev-parse', 'HEAD').stdout.decode().strip()
    if head != pin['commit']:
        raise SystemExit(f'{path}: source revision {head} differs from pin {pin["commit"]}')
    return False


def main():
    root = pathlib.Path.cwd()

    pins = json.loads((root / 'scripts/data/adreno-compiler-inputs.json').read_text())
    mesa = root / '.cache/mesa-work'
    print('pinned mesa:', pins['mesa']['commit'], flush=True)

    fresh = checkout(mesa, pins['mesa'])
    print('checkout:', 'created' if fresh else 'reused', flush=True)

    if fresh:
        for patch in pins['patches']:
            argv = ['git', '-C', mesa, 'apply', root / patch]
            r = run(*argv)
            if r.returncode:
                print('FAILED to apply', patch, flush=True)
                print(r.stderr.decode(errors='replace')[:3000], flush=True)
                return 1
            print('applied', pathlib.Path(patch).name, flush=True)

    print('--- validating against the pinned commit ---', flush=True)
    sys.path.insert(0, str(root / 'scripts'))
    from mesa_patch_identity import validate_recorded_patches

    validate_recorded_patches(root, mesa, pins)
    print('PASS: the patched tree reconstructs the pinned commit byte for byte', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
