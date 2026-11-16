"""Give the kernel link weak defaults for every 27 declaring source.

The iPadOS 27 patch series adds `extern ... weak_import` declarations to kernel
sources (kern_exec.c, bsd_init.c, IOKitBSDInit.cpp, and others). Upstream's
weak_defaults() generates zero definitions for BootLog.c only, so on a fresh
checkout of UniXNU@9931232 the arm64e link fails with:

    Undefined symbols for architecture arm64e.kernel:
      "_native_ram_block_gpu_addon" / "_native_ram_block_volume_seed
      "_native_source_storage_start"
      "_native_verified_block_manifest_sha384"
      "_native_verified_block_root_authorized"
      "_native_verified_block_volume_device"
      "_sheng_boot_watchdog_policy"

The declaring files live in tree/.cache/xnu-work, which device_source() does not
search (it looks in the package dirs, the device repo and the tree top level),
so the first attempt to feed them through weak_defaults() failed with
"kern/kern_exec.c not found under the device or build tree".

Instead of chasing those paths, this patch appends one generated file to the
storage archive's source list with the declarations the 27 series needs. The C
linker matches by name only; a uniform zeroed definition satisfies each import,
and a component's own strong definition wins when it is built.

Idempotent.

Usage:
    python patch-sheng-weak-coverage.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'scripts/build-sheng-source-storage.py'
MARK = 'patch-sheng-weak-coverage'

# Anchored on the call site patch-weak-defaults.py rewrites (it must run first:
# the list shape only exists after that patch has been applied).
LIST_ANCHOR = """        device_source('BluetoothProbe.cpp'),
    ]))"""

LIST_ADDED = """        device_source('BluetoothProbe.cpp'),
    ]))
    # patch-sheng-weak-coverage: the 27 patch series declares weak imports in
    # kernel sources that live under .cache/xnu-work, outside device_source()'s
    # search path. Append explicit zeroed definitions instead, so the arm64e
    # link resolves every symbol the series references. A component's own
    # strong definition always wins over these.
    extra_defaults = out / 'ShengWeakCoverage.c'
    extra_defaults.write_text(
        '#include <stdint.h>\\n'
        '/* patch-sheng-weak-coverage: zeroed defaults for the 27 series\\n'
        ' * weak imports (kern_exec.c, bsd_init.c, IOKitBSDInit.cpp). */\\n'
        '__attribute__((weak, visibility("hidden"))) int native_ram_block_gpu_addon(void) { return 0; }\\n'
        '__attribute__((weak, visibility("hidden"))) int native_ram_block_volume_seed(void) { return 0; }\\n'
        '__attribute__((weak, visibility("hidden"))) int native_source_storage_start(void) { return 0; }\\n'
        '__attribute__((weak, visibility("hidden"))) int native_verified_block_manifest_sha384(void) { return -1; }\\n'
        '__attribute__((weak, visibility("hidden"))) int native_verified_block_root_authorized(void) { return -1; }\\n'
        '__attribute__((weak, visibility("hidden"))) int native_verified_block_volume_device(void) { return -1; }\\n'
        '__attribute__((weak, visibility("hidden"))) long sheng_boot_watchdog_policy(void) { return 0; }\\n'
    )"""

SOURCES_ANCHOR = """               device_source('SourceRootBinding.cpp'), device_source('BootLog.c'), boot_log_defaults, device_source('BootReset.c'),"""

SOURCES_ADDED = """               device_source('SourceRootBinding.cpp'), device_source('BootLog.c'), boot_log_defaults, device_source('BootReset.c'), extra_defaults,"""


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

    changed = False
    if LIST_ANCHOR in text:
        text = text.replace(LIST_ANCHOR, LIST_ADDED, 1)
        changed = True
    elif 'ShengWeakCoverage.c' in text:
        print(f'{SCRIPT}: coverage file already written')
    else:
        raise SystemExit(f'{SCRIPT}: source list anchor not found; upstream changed')

    if SOURCES_ANCHOR in text:
        text = text.replace(SOURCES_ANCHOR, SOURCES_ADDED, 1)
        changed = True
    elif 'extra_defaults,' in text:
        print(f'{SCRIPT}: source list already extended')
    else:
        raise SystemExit(f'{SCRIPT}: archive source list not found; upstream changed')

    if changed:
        target.write_text(text, encoding='utf-8')
        print(f'{SCRIPT}: appended explicit weak coverage for the 27 series')
    return 0


if __name__ == '__main__':
    sys.exit(main())
