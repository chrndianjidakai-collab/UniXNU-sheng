"""Report where the payload path is declared, and change nothing.

This started as a patch that appended DiskIoDxe, Fat and the UEFI libraries to
sheng.dsc's [Components]. It was written from a wrong reading of the build: the
3.0 MiB SILICIUM_UEFI.fd was searched for ASCII module names and none appeared,
which looked like the modules were never compiled. They were. The volume nests
two containers and the names only exist after both are unpacked:

    boot.img kernel field
      gzip  -> 3.0 MiB FD   (SEC + one FV_IMAGE file; 47% used)
        LZMA -> 7.65 MiB FVMAIN
                  UniXNURamDiskDxe  DarwinBoot  DiskIoDxe
                  Fat  SimpleFileSystem  BlockIo   ... all present

The evidence is in the firmware build log, which lists the compiled objects:

    .../AARCH64/FatPkg/EnhancedFatDxe/Fat
    .../AARCH64/MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe
    .../AARCH64/MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe
    .../AARCH64/MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe
    .../AARCH64/DarwinBootPkg/Driver/DarwinBoot
    .../AARCH64/UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe

sheng.dsc lists the UniXNU and shengPkg modules; the MdeModulePkg and FatPkg
entries live in sheng.fdf's Include/DXE.inc, and EDK II compiles FDF-referenced
INFs that the DSC does not name. Adding them to the DSC as well is what made
GenFv abort on a duplicate file GUID.

So this script only prints the declaration sites. It is kept so the next reader
sees where the stack comes from before touching either file.

Usage:
    python report-sheng-payload-stack.py <uefi-sheng checkout>
"""
import pathlib
import re
import sys

DSC = 'Platforms/Xiaomi/shengPkg/sheng.dsc'
DXE = 'Platforms/Xiaomi/shengPkg/Include/DXE.inc'
CONFIG = 'Resources/Configs/sheng.toml'
WANTED = ('UniXNURamDiskDxe', 'DarwinBoot', 'DiskIoDxe', 'PartitionDxe',
          'Fat.inf', 'EnglishDxe')


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    for rel in (DSC, DXE, CONFIG):
        if not (root / rel).is_file():
            raise SystemExit(f'{root / rel} missing')

    dsc = (root / DSC).read_text(encoding='utf-8')
    dxe = (root / DXE).read_text(encoding='utf-8')
    config = (root / CONFIG).read_text(encoding='utf-8')

    print('declaration sites (DSC [Components] declares, DXE.inc places):')
    for name in WANTED:
        in_dsc = 'yes' if name in dsc else ' - '
        in_dxe = 'yes' if name in dxe else ' - '
        print(f'  {name:18s} DSC:{in_dsc:4s}  FDF/DXE.inc:{in_dxe}')

    match = re.search(r'\[uefi_fd\]([^\[]*)', config, re.S)
    if match:
        base = re.search(r'base\s*=\s*(0x[0-9a-fA-F]+)', match.group(1))
        size = re.search(r'size\s*=\s*(0x[0-9a-fA-F]+)', match.group(1))
        if base and size:
            print(f'\nflash device: base {base.group(1)} size {size.group(1)} '
                  f'({int(size.group(1), 16) / 1048576:.1f} MiB)')
            print('  This size is fixed by MemoryMapLib.c (UEFI FD row) and by')
            print('  check-sheng.py; the DXE phase lives inside it compressed.')

    print('\nNo change is needed: the shipped DSC and FDF already carry the')
    print('payload path, and a second copy in the DSC breaks GenFv on a file GUID.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
