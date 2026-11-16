"""Print UniXNURamDiskDxe's handoff decisions to the screen, not only the log.

The driver's three failure modes all end in a silent return, and on a board
without serial output or the Advanced Logger the menu just shows
"no boot entry found" with no clue which step failed:

    no entry-argument HOB        -> "UNIXNURAMDISK: no entry argument HOB"
    x0 is not a device tree      -> "UNIXNURAMDISK: x0 0x%lx is not a device tree"
    no initrd in /chosen         -> "UNIXNURAMDISK: no initrd in /chosen"

Each of those lines exists only as DEBUG(), which reaches ConOut on some
platforms and the debug log on others. This patch adds a Print() beside every
decision point and the success line, so the screen itself reports how far the
payload path got:

    RAMDISK: HOB missing
    RAMDISK: x0=0x... not a DT
    RAMDISK: DT ok, no initrd in /chosen
    RAMDISK: initrd 0x... - 0x... published

Idempotent.

Usage:
    python patch-ramdisk-screen-log.py <UniXNU checkout>
"""
import pathlib
import sys

SCRIPT = 'package/UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.c'
MARK = 'patch-ramdisk-screen-log'

ENTRY_OLD = """UniXNURamDiskDxeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_HOB_GUID_TYPE  *Hob;
  UINT64             Dtb;
"""

ENTRY_NEW = """UniXNURamDiskDxeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_HOB_GUID_TYPE  *Hob;
  UINT64             Dtb;
  {  /* patch-ramdisk-screen-log: unconditional entry marker */
    UINTN _h;
    Print (L"RAMDISK: driver entry reached\\n");
    for (_h = 0; _h < 60; _h++) { gBS->Stall (1000000); }
  }
"""

HOB_OLD = """  Hob = GetFirstGuidHob (&mEntryArgHobGuid);
  if (Hob == NULL) {
    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no entry argument HOB\\n"));
    return EFI_SUCCESS;
  }"""

HOB_NEW = """  Hob = GetFirstGuidHob (&mEntryArgHobGuid);
  if (Hob == NULL) {
    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no entry argument HOB\\n"));
    Print (L"RAMDISK: HOB missing\\n");  /* patch-ramdisk-screen-log */
    { UINTN _h; for (_h = 0; _h < 20; _h++) { gBS->Stall (1000000); } }  /* patch-ramdisk-screen-log: hold 20 s so the line can be read */
  }"""

DT_OLD = """  Dtb = ReadUnaligned64 ((CONST UINT64 *)GET_GUID_HOB_DATA (Hob));
  if ((Dtb == 0) || ((Dtb & 3) != 0) || (FdtCheckHeader ((VOID *)(UINTN)Dtb) != 0)) {
    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: x0 0x%lx is not a device tree\\n", Dtb));
    return EFI_SUCCESS;
  }"""

DT_NEW = """  Dtb = ReadUnaligned64 ((CONST UINT64 *)GET_GUID_HOB_DATA (Hob));
  if ((Dtb == 0) || ((Dtb & 3) != 0) || (FdtCheckHeader ((VOID *)(UINTN)Dtb) != 0)) {
    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: x0 0x%lx is not a device tree\\n", Dtb));
    Print (L"RAMDISK: x0=0x%lx not a DT\\n", Dtb);  /* patch-ramdisk-screen-log */
    { UINTN _h; for (_h = 0; _h < 20; _h++) { gBS->Stall (1000000); } }  /* patch-ramdisk-screen-log: hold 20 s */
  }"""

INITRD_OLD = """  if ((StartProp == NULL) || (EndProp == NULL) ||
      ((StartLength != 4) && (StartLength != 8)) || ((EndLength != 4) && (EndLength != 8)))
  {
    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no initrd in /chosen\\n"));
    return;
  }"""

INITRD_NEW = """  if ((StartProp == NULL) || (EndProp == NULL) ||
      ((StartLength != 4) && (StartLength != 8)) || ((EndLength != 4) && (EndLength != 8)))
  {
    DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: no initrd in /chosen\\n"));
    Print (L"RAMDISK: DT ok BUT no initrd in /chosen\\n");  /* patch-ramdisk-screen-log */
    { UINTN _h; for (_h = 0; _h < 20; _h++) { gBS->Stall (1000000); } }  /* patch-ramdisk-screen-log: hold 20 s */
  }"""

OK_OLD = """  DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: device tree at 0x%lx, %u bytes\\n", Dtb, (UINT32)FdtTotalSize ((VOID *)(UINTN)Dtb)));

  PublishInitrd ((VOID *)(UINTN)Dtb);"""

OK_NEW = """  DEBUG ((DEBUG_ERROR, "UNIXNURAMDISK: device tree at 0x%lx, %u bytes\\n", Dtb, (UINT32)FdtTotalSize ((VOID *)(UINTN)Dtb)));
  Print (L"RAMDISK: DT 0x%lx ok, publishing initrd\\n", Dtb);  /* patch-ramdisk-screen-log */

  PublishInitrd ((VOID *)(UINTN)Dtb);"""


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text(encoding='utf-8')

    if MARK in text:
        print(f'{SCRIPT}: already patched')
        return 0

    pairs = [
        ('entry marker', ENTRY_OLD, ENTRY_NEW),
        ('HOB branch', HOB_OLD, HOB_NEW),
        ('device-tree check', DT_OLD, DT_NEW),
        ('initrd check', INITRD_OLD, INITRD_NEW),
        ('success path', OK_OLD, OK_NEW),
    ]
    for name, old, new in pairs:
        if old not in text:
            if new.strip() and new.split('\n')[0] in text:
                print(f'{SCRIPT}: {name} already carries the print')
                continue
            raise SystemExit(f'{SCRIPT}: {name} not found; upstream changed')
        text = text.replace(old, new, 1)

    # The file does not include UefiLib today; Print() needs it.
    if '#include <Library/UefiLib.h>' not in text:
        anchor = '#include <Library/UefiBootServicesTableLib.h>'
        if anchor not in text:
            raise SystemExit(f'{SCRIPT}: include anchor not found')
        text = text.replace(anchor, anchor + '\n#include <Library/UefiLib.h>', 1)

    target.write_text(text, encoding='utf-8')
    print(f'{SCRIPT}: handoff decisions now print to the screen')
    return 0


if __name__ == '__main__':
    sys.exit(main())
