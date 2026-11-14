"""Make the RELEASE reference build link the same archives as the kernel build.

`scripts/build-fileset-release-reference.py` builds a second, symbol-bearing
RELEASE kernel that the prelink step uses for name matching. It hard-codes the
archives it links:

    archives = [root/'build/corecrypto-2023/libcorecrypto_kernel_noasm-namespaced.a']
    forced = [root/f'build/{folder}/{name}' for folder,name in (
        ('libpthread-kernel','libpthread_kernel.a'),
        ('armdt-platform','libArmDTPlatform.a'),
        ('armcpu','libArmCpu.a'))]

The real kernel build does not use that list. `build-xnu-4k-baseline.sh:793`
appends whatever the defconfig puts in `CONFIG_XNU_EXTRA_LD_ARCHIVES`, and
`sheng_ipados27_defconfig` carries

    CONFIG_XNU_EXTRA_LD_ARCHIVES="-Wl,-force_load,{tree}/build/sheng-source-storage/libShengSourceStorage.a"

which is where `BootWatchdogPolicy.c` and `SourceRootBinding.cpp` land. In that
archive are the definitions the iPadOS 27 kernel path needs:

    _sheng_boot_watchdog_policy              (BootWatchdogPolicy.c)
    _native_verified_block_volume_device     (SourceRootBinding.cpp)

The reference build never links it, so on 27 it dies with

    "_sheng_boot_watchdog_policy", referenced from _load_init_program in kern_exec.o
    "_native_verified_block_volume_device", referenced from _load_init_program in kern_exec.o
    ld: symbol(s) not found for architecture arm64e.kernel

This patch reads the same defconfig key the kernel build reads and appends those
archives to `forced`, so both builds agree. Absent or empty key = no change, which
keeps the 17 and 26 profiles exactly as they were.

Usage:
    python patch-fileset-reference.py <UniXNU checkout>
"""
import pathlib
import re
import sys

SCRIPT = 'scripts/build-fileset-release-reference.py'

OLD = """    forced = [root/f'build/{folder}/{name}' for folder,name in (
        ('libpthread-kernel','libpthread_kernel.a'),('armdt-platform','libArmDTPlatform.a'),('armcpu','libArmCpu.a'))]"""

NEW = """    forced = [root/f'build/{folder}/{name}' for folder,name in (
        ('libpthread-kernel','libpthread_kernel.a'),('armdt-platform','libArmDTPlatform.a'),('armcpu','libArmCpu.a'))]
    # The kernel build also force-loads whatever the defconfig lists in
    # CONFIG_XNU_EXTRA_LD_ARCHIVES; sheng_ipados27_defconfig points that at
    # build/sheng-source-storage/libShengSourceStorage.a, which defines
    # _sheng_boot_watchdog_policy and _native_verified_block_volume_device.
    # Without it the arm64e kernel path fails to link this reference build.
    # patch-fileset-reference.py added this; keep the parsing in step with
    # build-xnu-4k-baseline.sh:793.
    for extra in extra_ld_archives(root):
        if extra not in forced:
            forced.append(extra)"""

HELPER = '''def extra_ld_archives(root):
    """Archives named by CONFIG_XNU_EXTRA_LD_ARCHIVES for the selected profile.

    The kernel build receives the value through its make environment. Here the
    prepared XNU tree's .config is read instead: `unixnu` writes the composed
    configuration there before the kernel step runs. Entries look like
    "-Wl,-force_load,{tree}/build/.../libX.a", where {tree} is this root.
    """
    import shlex
    value = os.environ.get('XNU_EXTRA_LD_ARCHIVES', '')
    if not value:
        config = root / '.cache/xnu-work/.config'
        if config.is_file():
            for line in config.read_text(errors='replace').splitlines():
                name, _, raw = line.partition('=')
                if name.strip() == 'CONFIG_XNU_EXTRA_LD_ARCHIVES':
                    value = raw.strip().strip('"')
                    break
    archives = []
    for token in shlex.split(value):
        if not token.startswith('-Wl,-force_load,'):
            continue
        path = pathlib.Path(token.split(',', 2)[2].replace('{tree}', str(root)))
        if not path.is_absolute():
            path = root / path
        if path.is_file() and path not in archives:
            archives.append(path)
    return archives


'''

MARK = '# patch-fileset-reference.py: link the defconfig extra archives'


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text(encoding='utf-8')

    if 'extra_ld_archives' in text:
        print(f'{SCRIPT}: already patched')
        return 0
    if OLD not in text:
        raise SystemExit(f'{SCRIPT}: the forced list is not the expected shape; upstream changed')

    text = text.replace(OLD, NEW, 1)

    # Insert the helper just above def main(), and make sure pathlib is imported.
    anchor = 'def main():'
    if anchor not in text:
        raise SystemExit(f'{SCRIPT}: no def main() to anchor the helper')
    text = text.replace(anchor, HELPER + anchor, 1)
    if not re.search(r'^import pathlib$', text, re.M):
        text = text.replace('import os\n', 'import os\nimport pathlib\n', 1)

    target.write_text(text, encoding='utf-8')
    print(f'{SCRIPT}: reference build now links CONFIG_XNU_EXTRA_LD_ARCHIVES too')
    return 0


if __name__ == '__main__':
    sys.exit(main())
