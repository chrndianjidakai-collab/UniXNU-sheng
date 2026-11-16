"""Compile the UEFI disk and FAT stack so sheng.fdf can embed it.

sheng.fdf pulls the payload path in through !include Include/DXE.inc, and that
file names the whole stack:

    UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf   publishes the payload
    DarwinBootPkg/Driver/DarwinBoot.inf                      loads XNU from it
    MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf       block devices
    MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf partitions
    FatPkg/EnhancedFatDxe/Fat.inf                             the file system
    MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe/EnglishDxe.inf

sheng.dsc's [Components] section, however, lists only the UniXNU and shengPkg
modules. EDK II compiles what the DSC declares and only then lets the FDF place
it, so the four MdeModulePkg/FatPkg entries were never built: FvMain had their
INF lines and nothing behind them. The finished volume came out at 3.0 MB with
SEC, DxeCore and the UniXNU modules, no block or file-system protocol at all,
the boot manager listed no usable entry and every selection answered "no boot".

This adds those four modules to [Components]. It must not touch sheng.fdf: the
INF lines are already there and a second copy makes GenFv abort on a duplicate
file GUID, which is how the first attempt at this fix failed.

Idempotent.

Usage:
    python patch-sheng-dsc-components.py <uefi-sheng checkout>
"""
import pathlib
import sys

DSC = 'Platforms/Xiaomi/shengPkg/sheng.dsc'
MARK = 'patch-sheng-dsc-components: the payload disk and file-system stack'

ANCHOR = """  UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf
  shengPkg/Drivers/ShengKeyInputDxe/ShengKeyInputDxe.inf
  DarwinBootPkg/Driver/DarwinBoot.inf
"""

ADDED = """  UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf
  shengPkg/Drivers/ShengKeyInputDxe/ShengKeyInputDxe.inf
  DarwinBootPkg/Driver/DarwinBoot.inf
  # patch-sheng-dsc-components: the payload disk and file-system stack.
  # sheng.fdf's Include/DXE.inc already places these modules in FvMain, but a
  # module the DSC does not list is never compiled, so FvMain held their INF
  # names and no code. Without them the volume has no block or file-system
  # protocol, the payload never mounts, and the boot manager answers
  # "no boot" for every entry.
  MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf
  MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf
  MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe/EnglishDxe.inf
  FatPkg/EnhancedFatDxe/Fat.inf
"""


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    dsc = root / DSC
    if not dsc.is_file():
        raise SystemExit(f'{dsc} missing')
    text = dsc.read_text(encoding='utf-8')

    if MARK in text:
        print(f'{DSC}: already patched')
        return 0
    if ANCHOR not in text:
        raise SystemExit(f'{DSC}: anchor block not found; upstream changed')

    dsc.write_text(text.replace(ANCHOR, ADDED, 1), encoding='utf-8')
    print(f'{DSC}: added the disk and file-system modules to [Components]')
    return 0


if __name__ == '__main__':
    sys.exit(main())
