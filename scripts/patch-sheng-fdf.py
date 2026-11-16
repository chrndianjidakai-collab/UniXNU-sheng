"""Add the DXE drivers the payload path needs to sheng.fdf's FvMain.

sheng.dsc compiles nine modules, but sheng.fdf embeds only six of them in
FV.FvMain. The three it drops plus the UEFI file-system stack are exactly what
turns the payload volume into a bootable system:

    UniXNURamDiskDxe   publishes the payload FAT volume as a block device
    DarwinBoot         loads and starts the XNU kernel from that volume
    MdeModulePkg DiskIo / Partition / EnglishDxe / Fat  give EFI the block and
                       file-system protocols those two drivers read through

Without them the image still builds and still boots: SEC starts DxeCore, the
boot manager appears, and every entry answers "no boot" because no
EFI_SIMPLE_FILE_SYSTEM_PROTOCOL ever reaches the payload volume. That is the
failure this patch removes; it is a missing-module bug in the FDF, not a
property of the platform.

The same modules appear in the device record as the firmware contract
("The firmware DSC and FDF embed UniXNU, UniXNUDxe, DarwinBoot,
UniXNURamDiskDxe, DiskIoDxe and FAT support"), so this restores the documented
image rather than inventing a new one.

Idempotent: a second run reports "already patched".

Usage:
    python patch-sheng-fdf.py <uefi-sheng checkout>
"""
import pathlib
import sys

FDF = 'Platforms/Xiaomi/shengPkg/sheng.fdf'
MARK = 'patch-sheng-fdf: the payload file-system and loader stack'

ANCHOR = """  # IORT DT
  INF QcomPkg/Drivers/IortDtDxe/IortDtDxe.inf
"""

ADDED = """  # IORT DT
  INF QcomPkg/Drivers/IortDtDxe/IortDtDxe.inf

  # patch-sheng-fdf: the payload file-system and loader stack. sheng.dsc
  # compiles these (and the DSC lists the two UniXNU ones), but FvMain did not
  # embed them, so the finished image could not mount the payload volume and
  # answered "no boot" from the boot manager. Order matters: the block and
  # file-system producers come before the consumers that depend on them.
  INF MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf
  INF MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf
  INF MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe/EnglishDxe.inf
  INF FatPkg/EnhancedFatDxe/Fat.inf
  INF UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf
  INF DarwinBootPkg/Driver/DarwinBoot.inf
"""

# The FDF also has to list the same modules under [Components]-style DSC
# consumption for FatPkg and the MdeModulePkg disk drivers: sheng.dsc only
# names the UniXNU and shengPkg ones today. Add them to the DSC too.
DSC = 'Platforms/Xiaomi/shengPkg/sheng.dsc'
DSC_MARK = 'patch-sheng-fdf: disk and FAT components'
DSC_ANCHOR = """  UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf
"""
DSC_ADDED = """  UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf
  # patch-sheng-fdf: disk and FAT components the payload path reads through.
  MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf
  MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf
  MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe/EnglishDxe.inf
  FatPkg/EnhancedFatDxe/Fat.inf
"""


def patch(path, mark, anchor, added):
    text = path.read_text(encoding='utf-8')
    if mark in text:
        print(f'{path.name}: already patched')
        return False
    if anchor not in text:
        raise SystemExit(f'{path}: anchor block not found; upstream changed')
    path.write_text(text.replace(anchor, added, 1), encoding='utf-8')
    print(f'{path.name}: added the payload file-system and loader modules')
    return True


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    fdf = root / FDF
    dsc = root / DSC
    for target in (fdf, dsc):
        if not target.is_file():
            raise SystemExit(f'{target} missing')
    patch(fdf, MARK, ANCHOR, ADDED)
    patch(dsc, DSC_MARK, DSC_ANCHOR, DSC_ADDED)
    return 0


if __name__ == '__main__':
    sys.exit(main())
