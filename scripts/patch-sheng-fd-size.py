"""Size the sheng flash device for the modules the payload path needs.

sheng.toml carries [uefi_fd] size = 0x300000 (3 MiB), the same value the other
device configs use. GenFv builds exactly that container, so FV.FvMain can hold
six small modules and nothing more. Adding the UEFI disk and FAT stack to
sheng.fdf then fails:

    GenFv: ERROR 2000: Invalid parameter
    error 7000: Failed to generate FV

The sheng UEFI the vendor ships is not a 3 MiB volume: the official fastboot
archive's uefi.elf is a 44.51 MB PE32+ image (0x2d30000 SizeOfImage, .text
0x29d0000 and .data 0x350000) with ImageBase 0, so the bootloader maps it where
it likes and the 0xA7100000 base in this config plays no part in that image's
placement. The 3 MiB value is a leftover from the devices this template was
copied from, not a property of sheng.

48 MiB gives FvMain room for the disk/FAT stack, UniXNURamDiskDxe, DarwinBoot
and the shengPkg drivers the DSC already compiles, with headroom for growth.

Idempotent: a second run reports "already sized".

Usage:
    python patch-sheng-fd-size.py <uefi-sheng checkout>
"""
import pathlib
import re
import sys

CONFIG = 'Resources/Configs/sheng.toml'
TARGET = 0x3000000
COMMENT = '   # 48 MiB: the disk/FAT stack and DarwinBoot need the room'


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    config = root / CONFIG
    if not config.is_file():
        raise SystemExit(f'{config} missing')
    text = config.read_text(encoding='utf-8')

    block = re.search(r'\[uefi_fd\]([^\[]*)', text, re.S)
    if not block:
        raise SystemExit(f'{CONFIG}: no [uefi_fd] section; upstream changed')
    body = block.group(1)
    size = re.search(r'size\s*=\s*(0x[0-9a-fA-F]+)', body)
    if not size:
        raise SystemExit(f'{CONFIG}: [uefi_fd] has no size; upstream changed')

    current = int(size.group(1), 16)
    if current >= TARGET:
        print(f'{CONFIG}: [uefi_fd] size is already {size.group(1)}')
        return 0

    new_body = body[:size.start(1)] + hex(TARGET) + COMMENT + body[size.end(1):]
    text = text[:block.start(1)] + new_body + text[block.end(1):]
    config.write_text(text, encoding='utf-8')
    print(f'{CONFIG}: [uefi_fd] size {hex(current)} -> {hex(TARGET)} (48 MiB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
