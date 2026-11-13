"""Patch extract-sheng-firmware.py so the WCN7850 inputs are retained.

The stock selection regex at extract-sheng-firmware.py:47 keeps only

    xbl* uefi* abl aop* devcfg hyp tz dtbo boot vendor_boot init_boot

so the three files `firmware/wcn7850/manifest.json` pins -- amss.bin, m3.bin,
board-2.bin -- are streamed past and thrown away. The firmware step then
succeeds, and the payload step dies much later with

    FileNotFoundError: .../device/firmware/wcn7850/amss.bin

This patch widens the selection to those three names and stages them where
`scripts/build-wifi-userspace.py` looks. Nothing else changes: the archive
verification, the streaming reader and the manifest record keep their
behaviour.

Usage:
    python patch-extract-firmware.py <UniXNU-or-device checkout>
"""
import pathlib
import sys

SCRIPT = 'scripts/extract-sheng-firmware.py'

OLD = ("firmware = re.compile(r'^(xbl[^/]*|uefi[^/]*|abl|aop[^/]*|devcfg|hyp|tz|dtbo|boot|vendor_boot|init_boot)\\.(elf|img|bin|mbn)$')")

NEW = (
    "# WCN7850 Wi-Fi/BT firmware: firmware/wcn7850/manifest.json pins these three\n"
    "# files, and scripts/build-wifi-userspace.py reads them from the device tree.\n"
    "# The stock pattern above drops them, so the build failed later with\n"
    "# FileNotFoundError on firmware/wcn7850/amss.bin.\n"
    "wcn = re.compile(r'^(amss|m3|board-2)\\.bin$')\n"
    "firmware = re.compile(r'^(xbl[^/]*|uefi[^/]*|abl|aop[^/]*|devcfg|hyp|tz|dtbo|boot|vendor_boot|init_boot)\\.(elf|img|bin|mbn)$')"
)

OLD_RETAIN = """            retain = firmware.fullmatch(name.lower()) or (
                member.size < 1024 * 1024 and
                (name.startswith('flash_all') or name.lower() in ('md5sum.xml', 'partition.xml', 'android-info.txt')))"""

NEW_RETAIN = """            retain = (firmware.fullmatch(name.lower()) or wcn.fullmatch(name.lower()) or (
                member.size < 1024 * 1024 and
                (name.startswith('flash_all') or name.lower() in ('md5sum.xml', 'partition.xml', 'android-info.txt'))))"""

# The staged files must also land in firmware/wcn7850/, not only porting-inputs/.
OLD_TAIL = """manifest_path = directory / 'porting-inputs.json'"""

NEW_TAIL = """# The WCN7850 binaries belong in the device tree so the payload step finds them.
wcn_source = directory / 'porting-inputs'
wcn_target = Path(os.environ.get('UNIXNU_DEVICE') or ROOT) / 'firmware/wcn7850'
for entry in selected:
    if entry['file'].lower() in ('amss.bin', 'm3.bin', 'board-2.bin'):
        wcn_target.mkdir(parents=True, exist_ok=True)
        staged = wcn_source / entry['file']
        destination = wcn_target / entry['file']
        if destination.is_file() and destination.read_bytes() == staged.read_bytes():
            print(f'WCN7850 input already staged: {entry["file"]}', flush=True)
        else:
            import shutil as _shutil
            _shutil.copyfile(staged, destination)
            print(f'Staged WCN7850 input: {destination} ({entry["bytes"]} bytes)', flush=True)

manifest_path = directory / 'porting-inputs.json'"""


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text()

    if 'wcn = re.compile' in text:
        print(f'{SCRIPT}: already patched')
        return 0

    for old, new, label in ((OLD, NEW, 'selection regex'),
                            (OLD_RETAIN, NEW_RETAIN, 'retain expression'),
                            (OLD_TAIL, NEW_TAIL, 'staging tail')):
        if old not in text:
            raise SystemExit(f'{SCRIPT}: could not find the {label}; the upstream file changed')
        text = text.replace(old, new, 1)

    target.write_text(text)
    print(f'{SCRIPT}: patched in {root}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
