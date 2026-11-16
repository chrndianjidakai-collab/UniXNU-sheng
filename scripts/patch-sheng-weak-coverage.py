"""Give the kernel link weak defaults for every file that declares weak imports.

Upstream's weak_defaults() generates zero-valued definitions for the weak
imports of one file — BootLog.c — and the iPadOS 27 profile needs exactly that
coverage for those symbols. But the 27 patch series also carries weak_import
declarations in other kernel sources, and after the pin moved to UniXNU@9931232
those declarations have no definitions at link time:

    Undefined symbols for architecture arm64e.kernel:
      "_native_ram_block_gpu_addon"            (kern_exec.o)
      "_native_ram_block_volume_seed"          (kern_exec.o)
      "_native_source_storage_start"           (bsd_init.o)
      "_native_verified_block_manifest_sha384" (IOKitBSDInit.cpp)
      "_native_verified_block_root_authorized" (IOKitBSDInit.cpp)
      "_native_verified_block_volume_device"   (IOKitBSDInit.cpp)
      "_sheng_boot_watchdog_policy"
      "_iokit_physical_descriptor_close_notify"
      "_ml_static_mfree_prepare"

The patch extends the same call that already writes BootLogDefaults.c so it
also writes defaults for the other declaring sources, then adds the generated
files to the build's source list. weak_defaults() itself is untouched: it is
already generic over whatever file it is given.

Idempotent; each insertion is anchored and refuses to double-apply.

Usage:
    python patch-sheng-weak-coverage.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'scripts/build-sheng-source-storage.py'
MARK = 'patch-sheng-weak-coverage'

OLD = """    boot_log_defaults = out / 'BootLogDefaults.c'
    boot_log_defaults.write_text(weak_defaults(device_source('BootLog.c')))"""

NEW = """    boot_log_defaults = out / 'BootLogDefaults.c'
    boot_log_defaults.write_text(weak_defaults(device_source('BootLog.c')))
    # patch-sheng-weak-coverage: the 27 patch series declares weak imports in
    # kernel sources other than BootLog.c, and every one of them fails the
    # arm64e link without a definition:
    #   _native_ram_block_gpu_addon / _native_ram_block_volume_seed
    #       (kern_exec.c), _native_source_storage_start (bsd_init.c),
    #   _native_verified_block_manifest_sha384 / _root_authorized /
    #       _volume_device (IOKitBSDInit.cpp),
    #   _sheng_boot_watchdog_policy, _iokit_physical_descriptor_close_notify,
    #   _ml_static_mfree_prepare.
    # weak_defaults() is generic over its input file, so give it these sources
    # too and compile the results into the archive.
    import os as _os
    weak_extra = []
    for relative in ('kern/kern_exec.c', 'bsd/bsd_init.c',
                     'iokit/bsd/IOKitBSDInit.cpp', 'osfmk/kern/locks.c'):
        source_file = device_source(relative)
        if not source_file.read_text(errors='replace').count('weak_import'):
            continue
        generated = out / (pathlib.Path(relative).stem + 'WeakDefaults.c')
        text_now = weak_defaults(source_file)
        if not text_now.strip():
            continue
        generated.write_text(text_now)
        weak_extra.append(generated)
        print(f'weak defaults for {relative}: {text_now.count(chr(10))} lines', flush=True)
    _ = _os.name  # keep the import meaningful without changing the signature
"""

OLD_SOURCES = """               device_source('SourceRootBinding.cpp'), device_source('BootLog.c'), boot_log_defaults, device_source('BootReset.c'),"""

NEW_SOURCES = """               device_source('SourceRootBinding.cpp'), device_source('BootLog.c'), boot_log_defaults, device_source('BootReset.c'), *weak_extra,"""


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text(encoding='utf-8')

    if MARK in text:
        print(f'{SCRIPT}: already patched')
        return 0
    if OLD not in text:
        raise SystemExit(f'{SCRIPT}: BootLogDefaults block not found; upstream changed')
    if OLD_SOURCES not in text:
        raise SystemExit(f'{SCRIPT}: source list not found; upstream changed')

    text = text.replace(OLD, NEW, 1)
    text = text.replace(OLD_SOURCES, NEW_SOURCES, 1)
    target.write_text(text, encoding='utf-8')
    print(f'{SCRIPT}: weak_defaults now covers the 27 declaring sources')
    return 0


if __name__ == '__main__':
    sys.exit(main())
