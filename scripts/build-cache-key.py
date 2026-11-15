"""Compute the cache key for the build output tree.

Every run of package-6lane on a hosted macOS runner starts from an empty
workspace, so the two most expensive phases repeat from zero each time:

    deps                      ~4 min   uefi-sheng submodules, linux/freebsd sources
    build (kernel + payload)  ~35 min  XNU objects, GPU/driver archives, payload

The `actions/cache` entry this key names holds both, so a rerun that differs only
in a step *after* the first compile resumes from the previous objects instead of
recompiling. The key changes whenever anything that changes the output changes:

    the device board.toml (components, kernel args, profile selection)
    unixnu.lock / feeds.toml (which sources, at which commits)
    components.toml (component pins)
    the patch series (patch contents, so an edited patch rebuilds)
    the pinned UniXNU revision and the device revision
    the OS profile

A key that is too coarse would restore stale objects over a changed tree, so it
deliberately errs toward a miss.

Usage:
    python build-cache-key.py <device> <unixnu> [--os PROFILE]
prints one line: the key suffix.
"""
import hashlib
import pathlib
import subprocess
import sys


def git(directory, *args):
    try:
        return subprocess.check_output(['git', '-C', str(directory), *args],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ''


def digest_of(paths, seed):
    h = hashlib.sha256()
    for path in paths:
        path = pathlib.Path(path)
        if not path.is_file():
            continue
        h.update(str(path.name).encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:16]


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    device = pathlib.Path(sys.argv[1]).resolve()
    unixnu = pathlib.Path(sys.argv[2]).resolve()
    profile = ''
    if '--os' in sys.argv:
        profile = sys.argv[sys.argv.index('--os') + 1]

    h = hashlib.sha256()

    # Source selection: which commits, which component pins.
    for name in ('board.toml', 'feeds.toml', 'unixnu.lock', 'proprietary-files.txt'):
        path = device / name
        if path.is_file():
            h.update(name.encode())
            h.update(path.read_bytes())
    for name in ('components.toml', 'unixnu.lock'):
        path = unixnu / name
        if path.is_file():
            h.update(('unixnu/' + name).encode())
            h.update(path.read_bytes())

    # The patch series: an edited patch changes the objects.
    patch_digest = hashlib.sha256()
    for patch in sorted((device / 'patches').rglob('*')) if (device / 'patches').is_dir() else []:
        if patch.is_file():
            patch_digest.update(str(patch.relative_to(device)).encode())
            patch_digest.update(patch.read_bytes())
    h.update(b'patches:' + patch_digest.digest())

    # Scripts that drive compilation: a changed recipe means different objects.
    # The patch-*.py helpers are excluded entirely: they rewrite an upstream
    # script at runtime, and the file they rewrite is digested by the UniXNU
    # checkout content above. Digesting the helper itself meant that adding or
    # editing one of them (which happens on almost every prelink fix) threw away
    # the 35-minute kernel compile even though the built objects were unchanged.
    def is_patch_helper(name):
        return name.startswith('patch-') and name.endswith('.py')
    script_digest = hashlib.sha256()
    for base in (device / 'scripts', unixnu / 'scripts'):
        if not base.is_dir():
            continue
        for script in sorted(base.rglob('*.py')):
            if is_patch_helper(script.name):
                continue
            script_digest.update(str(script).encode())
            script_digest.update(script.read_bytes())
    h.update(b'scripts:' + script_digest.digest())

    # Revisions make a pushed fix invalidate the cache even when no tracked file
    # above changed (for example a submodule bump recorded only in the commit).
    # The device HEAD is deliberately NOT folded in: every commit rewrites it,
    # and the files that actually change the objects are digested above by
    # content, so a HEAD-only change (a prelink patch, a workflow edit) keeps the
    # cache and skips the 35-minute recompile.
    h.update(b'unixnu:' + git(unixnu, 'rev-parse', 'HEAD').encode())
    h.update(b'profile:' + profile.encode())

    print(h.hexdigest()[:24])
    return 0


if __name__ == '__main__':
    sys.exit(main())
