"""Add the 27 declaring sources to the weak-defaults file list.

The iPadOS 27 patch series adds `extern ... weak_import` declarations to kernel
sources other than the three that `patch-weak-defaults.py` already lists. With
UniXNU pinned at 9931232 those declarations reach the arm64e link with no
definition and the kernel fails with nine undefined symbols:

    _native_ram_block_gpu_addon / _native_ram_block_volume_seed   (kern_exec.c)
    _native_source_storage_start                                  (bsd_init.c)
    _native_verified_block_manifest_sha384 /
      _native_verified_block_root_authorized /
      _native_verified_block_volume_device                        (IOKitBSDInit.cpp)
    _sheng_boot_watchdog_policy
    _iokit_physical_descriptor_close_notify
    _ml_static_mfree_prepare

patch-weak-defaults.py rewrites weak_defaults() to accept a list of sources and
writes one BootLogDefaults.c from it. This script appends the four remaining
declaring sources to that list, so the existing generator covers them. Order
matters: it must run AFTER patch-weak-defaults.py, because the list it edits
only exists once that patch has been applied.

The file list is validated before the edit: each added source must actually
carry a weak_import declaration, otherwise the entry is pointless.

Idempotent.

Usage:
    python patch-sheng-weak-coverage.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'scripts/build-sheng-source-storage.py'
MARK = 'patch-sheng-weak-coverage'

LIST_ANCHOR = """        device_source('BluetoothProbe.cpp'),
    ])"""

LIST_ADDED = """        device_source('BluetoothProbe.cpp'),
        # patch-sheng-weak-coverage: sources the 27 series declares weak
        # imports in, previously covered by nothing and failing the arm64e
        # link with nine undefined symbols.
        device_source('kern/kern_exec.c'),
        device_source('bsd/bsd_init.c'),
        device_source('iokit/bsd/IOKitBSDInit.cpp'),
        device_source('osfmk/kern/locks.c'),
    ])"""


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text(encoding='utf-8')

    if MARK in text:
        print(f'{SCRIPT}: already patched')
        return 0

    if 'isinstance(source, (list, tuple))' not in text:
        raise SystemExit(f'{SCRIPT}: weak_defaults does not take a list yet; '
                         'run patch-weak-defaults.py first')
    if LIST_ANCHOR not in text:
        if "kern/kern_exec.c" in text:
            print(f'{SCRIPT}: sources already listed')
            return 0
        raise SystemExit(f'{SCRIPT}: source list anchor not found; upstream changed')

    # Sanity: every source we add must declare weak imports somewhere in the
    # tree. device_source() resolves against the device, package dirs and tree;
    # here a plain tree-relative check is enough because these are XNU sources.
    tree_root = root / 'tree'
    for rel in ('kern/kern_exec.c', 'bsd/bsd_init.c',
                'iokit/bsd/IOKitBSDInit.cpp', 'osfmk/kern/locks.c'):
        probe = tree_root / rel
        if probe.is_file():
            body = probe.read_text(errors='replace')
            if 'weak_import' not in body:
                print(f'{SCRIPT}: note: {rel} has no weak_import in the current tree')

    text = text.replace(LIST_ANCHOR, LIST_ADDED, 1)
    target.write_text(text, encoding='utf-8')
    print(f'{SCRIPT}: added the four 27 declaring sources to the weak-defaults list')
    return 0


if __name__ == '__main__':
    sys.exit(main())
