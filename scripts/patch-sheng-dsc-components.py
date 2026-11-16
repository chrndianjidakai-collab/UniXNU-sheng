"""Complete the sheng DSC the way the porting guide requires.

The guide's "Required integration" section names six modules that must be
listed under DSC [Components] (and placed by the FDF), plus the shared
libraries their drivers consume:

    UniXNUPkg/Application/UniXNU/UniXNU.inf
    UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf
    DarwinBootPkg/Driver/DarwinBoot.inf
    UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf
    MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf
    FatPkg/EnhancedFatDxe/Fat.inf
  [LibraryClasses]
    HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf
    FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf

sheng.dsc listed the four UniXNU/shengPkg entries but not DiskIoDxe or Fat,
and its [LibraryClasses] did not map HobLib/FdtLib. sheng.fdf's
Include/DXE.inc already carries the INF lines, so the FDF needs no edit: the
modules simply had no compiled body to place. The resulting 3.0 MB volume held
SEC, DxeCore and the UniXNU modules, no block or file-system protocol, the menu
listed nothing, and every selection answered "no boot" — exactly the state the
guide's payload-discovery checklist starts from.

PartitionDxe is deliberately absent: it is only needed when the payload uses a
partition table, and this payload is a raw FAT volume.

The flash device size is NOT touched. MemoryMapLib.c maps
    FD Reserved       0xA7000000 0x00100000
    UEFI FD           0xA7100000 0x00300000
    UEFI FD Reserved  0xA7400000 0x00200000
    Info Blk / MMU PageTables immediately after
and check-sheng.py refuses any [uefi_fd] size that disagrees with that table.
The FAT stack is a few hundred KB and the guide says a supplied .fd must match
the board's base and size, so the volume grows inside 0x300000 or the build
fails on space — which is the signal to trim something else instead.

Idempotent.

Usage:
    python patch-sheng-dsc-components.py <uefi-sheng checkout>
"""
import pathlib
import sys

DSC = 'Platforms/Xiaomi/shengPkg/sheng.dsc'
COMP_MARK = 'patch-sheng-dsc-components: disk and FAT modules'
LIB_MARK = 'patch-sheng-dsc-components: libraries for the disk and FAT modules'

COMP_ANCHOR = """  DarwinBootPkg/Driver/DarwinBoot.inf
"""

COMP_ADDED = """  DarwinBootPkg/Driver/DarwinBoot.inf
  # patch-sheng-dsc-components: disk and FAT modules. sheng.fdf's
  # Include/DXE.inc already places them in the firmware volume, but EDK II
  # compiles only what the DSC lists, so the INF lines had no code behind them
  # and the finished volume carried no block or file-system protocol.
  MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf
  FatPkg/EnhancedFatDxe/Fat.inf
  MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe/EnglishDxe.inf
"""

# HobLib/FdtLib are what UniXNURamDiskDxe reads the handoff FDT through; they
# belong in [LibraryClasses] as a DXE mapping. Anchor on the existing DXE
# library block so the insertion order stays valid.
LIB_ANCHOR = """[LibraryClasses]

  #
  # DXE phase
  #
"""

LIB_ADDED = """[LibraryClasses]

  #
  # DXE phase
  #

  # patch-sheng-dsc-components: libraries for the disk and FAT modules.
  HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf
  FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf
"""


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    dsc = root / DSC
    if not dsc.is_file():
        raise SystemExit(f'{dsc} missing')
    text = dsc.read_text(encoding='utf-8')
    changed = False

    if COMP_MARK not in text:
        if COMP_ANCHOR not in text:
            raise SystemExit(f'{DSC}: [Components] anchor not found; upstream changed')
        text = text.replace(COMP_ANCHOR, COMP_ADDED, 1)
        print(f'{DSC}: added DiskIoDxe, Fat and EnglishDxe to [Components]')
        changed = True

    if LIB_MARK not in text:
        # Only add a mapping the DSC does not already carry. sheng.dsc defines
        # FdtLib in a later [LibraryClasses] block, and a duplicate definition
        # for the same arch and module type is what EDK II rejects.
        additions = []
        if 'HobLib|' not in text:
            additions.append('  HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf')
        if 'FdtLib|' not in text:
            additions.append('  FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf')
        if additions:
            index = text.find('[LibraryClasses]\n')
            if index < 0:
                raise SystemExit(f'{DSC}: no [LibraryClasses] section; upstream changed')
            insert = index + len('[LibraryClasses]\n')
            block = ('\n  # patch-sheng-dsc-components: libraries for the disk and FAT modules.\n'
                     + '\n'.join(additions) + '\n')
            text = text[:insert] + block + text[insert:]
            print(f'{DSC}: mapped {len(additions)} library class(es) in [LibraryClasses]')
            changed = True
        else:
            print(f'{DSC}: HobLib and FdtLib already mapped')

    if not changed:
        print(f'{DSC}: already patched')
        return 0

    dsc.write_text(text, encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
