"""Make the RELEASE reference build link the same archives as the kernel build.

`scripts/build-fileset-release-reference.py` hard-codes the archives it links:

    forced = [root/f'build/{folder}/{name}' for folder,name in (
        ('libpthread-kernel','libpthread_kernel.a'),
        ('armdt-platform','libArmDTPlatform.a'),
        ('armcpu','libArmCpu.a'))]

The real kernel build also force-loads the board's own storage archive through
CONFIG_XNU_EXTRA_LD_ARCHIVES — `sheng_ipados27_defconfig` points it at
build/sheng-source-storage/libShengSourceStorage.a, which defines
_sheng_boot_watchdog_policy (BootWatchdogPolicy.c) and
_native_verified_block_volume_device (SourceRootBinding.cpp). The comparison
kernel without it dies on the arm64e link.

History of getting this wrong, so it is not repeated:
  v1 read <tree>/.cache/xnu-work/.config  — no such file
  v2 read <tree>/.config                  — the composed config is one level UP,
                                            at out/<profile>/<config>/.config
  (the CONFIG_XNU_EXTRA_LD_ARCHIVES environment variable that xnu_env() exports
   was expected to cover this; the identical "removed 67" outcome in #31 shows
   the resolution chain still came up empty, and its failure mode was invisible)

v4 stops resolving through indirection: the archive path is known and fixed, so
the patch appends it explicitly and PRINTS the resolved forced list. If it still
fails, the tail of the reference build log is printed too, so the linker's own
error reaches the GitHub job log instead of dying silently on the runner.

Usage:
    python patch-fileset-reference.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'scripts/build-fileset-release-reference.py'

FORCED_OLD = """    forced = [root/f'build/{folder}/{name}' for folder,name in (
        ('libpthread-kernel','libpthread_kernel.a'),('armdt-platform','libArmDTPlatform.a'),('armcpu','libArmCpu.a'))]"""

FORCED_NEW = """    forced = [root/f'build/{folder}/{name}' for folder,name in (
        ('libpthread-kernel','libpthread_kernel.a'),('armdt-platform','libArmDTPlatform.a'),('armcpu','libArmCpu.a'))]
    # patch-fileset-reference.py: the kernel build force-loads the board's own
    # storage archive through CONFIG_XNU_EXTRA_LD_ARCHIVES
    # (sheng_ipados27_defconfig); the comparison build must link it too, or the
    # arm64e link fails on _sheng_boot_watchdog_policy and
    # _native_verified_block_volume_device. The file exists by the time this
    # script runs: archive-08 (build-sheng-source-storage) precedes archive-20.
    extra = root / 'build/sheng-source-storage/libShengSourceStorage.a'
    if extra.is_file() and extra not in forced:
        forced.append(extra)
    print('reference forced archives:', flush=True)
    for p in forced:
        print('  ', p, '(present)' if p.is_file() else '(MISSING)', flush=True)"""

RAISE_OLD = """    print('RELEASE reference exit', result.returncode, 'log', output / f'{mode}-build.log', flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)"""

RAISE_NEW = """    print('RELEASE reference exit', result.returncode, 'log', output / f'{mode}-build.log', flush=True)
    if result.returncode:
        tail = (output / f'{mode}-build.log').read_text(errors='replace')[-6000:]
        print('---- reference build log tail (diagnostics) ----', flush=True)
        print(tail, flush=True)
        raise SystemExit(result.returncode)"""


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text(encoding='utf-8')

    if 'reference forced archives:' in text:
        print(f'{SCRIPT}: already carries the v4 patch')
        return 0

    changed = False
    if FORCED_OLD in text:
        text = text.replace(FORCED_OLD, FORCED_NEW, 1)
        changed = True
        print(f'{SCRIPT}: appended the storage archive to the forced list')
    elif "extra = root / 'build/sheng-source-storage" not in text:
        raise SystemExit(f'{SCRIPT}: forced list not found in the expected shape; upstream changed')

    if RAISE_OLD in text:
        text = text.replace(RAISE_OLD, RAISE_NEW, 1)
        changed = True
        print(f'{SCRIPT}: failures now print the reference build log tail')
    elif 'reference build log tail (diagnostics)' in text:
        pass  # already carried from a previous run of this script
    else:
        print(f'{SCRIPT}: warning: raise block not found; failure diagnostics not added')

    if not changed:
        print(f'{SCRIPT}: nothing to change')
        return 0

    target.write_text(text, encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
