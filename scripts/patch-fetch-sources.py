"""Add a second step to fetch-sources.py: the non-cone sparse checkout check.

`tools/source-lock.json` lists a few single files among its sparse paths
("net/core/skbuff.c", "lib/rbtree.c", "lib/crypto/arc4.c",
"drivers/soc/qcom/qmi_interface.c", "drivers/soc/qcom/qmi_encdec.c").
The stock fetch-sources.py hands the whole array to

    git -C deps/<name> sparse-checkout add <paths...>

which accepts directories only:

    fatal: 'net/core/skbuff.c' is not a directory; to treat it as a directory
           anyway, rerun with --skip-checks

`fix-ath12k-sparse-paths.py` moves those entries into a `files` list. This patch
makes fetch-sources.py use it: directories still go to `sparse-checkout add`,
and each file is staged with `git checkout <commit> -- <file>`.

Usage:
    python patch-fetch-sources.py <Ath12kWifi checkout>
"""
import pathlib
import sys

SCRIPT = 'tools/fetch-sources.py'

OLD = """    if not check_only:
        subprocess.run(["git", "-C", str(directory), "sparse-checkout", "add", *source["paths"]], check=True)"""

NEW = """    if not check_only:
        # Only directories may be passed to `sparse-checkout add`; a file entry
        # makes git abort with "is not a directory". fix-ath12k-sparse-paths.py
        # moves those entries into `files`, and they are staged one by one here.
        if source["paths"]:
            subprocess.run(["git", "-C", str(directory), "sparse-checkout", "add", *source["paths"]],
                           check=True)
        for path in source.get("files", []):
            subprocess.run(["git", "-C", str(directory), "checkout", source["commit"], "--", path],
                           check=True)"""


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    target = root / SCRIPT
    if not target.is_file():
        raise SystemExit(f'{target} missing')
    text = target.read_text()

    if 'Only directories may be passed to `sparse-checkout add`' in text:
        print(f'{SCRIPT}: already patched')
        return 0
    if OLD not in text:
        raise SystemExit(f'{SCRIPT}: could not find the sparse-checkout call; upstream changed')

    target.write_text(text.replace(OLD, NEW, 1))
    print(f'{SCRIPT}: patched to stage single files with git checkout')
    return 0


if __name__ == '__main__':
    sys.exit(main())
