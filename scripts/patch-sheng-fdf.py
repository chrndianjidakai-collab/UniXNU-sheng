"""Report where the payload file-system stack actually lives in sheng.fdf.

An earlier revision of this script appended the UEFI disk and FAT stack to
FV.FvMain. That was wrong twice over: the modules are already there, pulled in
through !include Include/DXE.inc and Include/APRIORI.inc, and appending them a
second time made GenFv fail outright:

    GenFv: ERROR 2000: Invalid parameter
    the 23th file and 44th file have the same file GUID.

So this script only reports the layout, and stays in the tree as the record of
where the stack comes from, so a future change does not add it a third time.
It performs no change.

Usage:
    python report-sheng-fdf.py <uefi-sheng checkout>
"""
import pathlib
import re
import sys

FDF = 'Platforms/Xiaomi/shengPkg/sheng.fdf'
INCLUDES = ('APRIORI.inc', 'DXE.inc', 'RAW.inc')
NEEDED = ('DiskIoDxe', 'PartitionDxe', 'Fat.inf', 'RamDisk', 'DarwinBoot')


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    fdf = root / FDF
    if not fdf.is_file():
        raise SystemExit(f'{fdf} missing')

    text = fdf.read_text(encoding='utf-8')
    print('sheng.fdf includes:')
    for name in re.findall(r'!include\s+(\S+)', text):
        print(f'  {name}')

    target = fdf.parent / 'Include'
    found = {}
    for name in INCLUDES:
        path = target / name
        if not path.is_file():
            continue
        body = path.read_text(encoding='utf-8')
        for need in NEEDED:
            for match in re.finditer(r'^\s*INF\s+(\S*' + re.escape(need) + r'\S*)', body, re.M):
                found.setdefault(need, []).append(f'{name}: {match.group(1)}')

    print()
    for need in NEEDED:
        hits = found.get(need)
        if hits:
            print(f'{need:12s} already embedded:')
            for hit in hits:
                print(f'  {hit}')
        else:
            print(f'{need:12s} NOT in the include files')
    print()
    print('The disk/FAT stack is part of these includes; do not add it to FvMain')
    print('again (a duplicate file GUID makes GenFv fail).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
