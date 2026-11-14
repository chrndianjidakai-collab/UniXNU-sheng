"""Make fetch-sources.py able to stage single-file sparse entries.

`tools/fetch-sources.py` clones a source as

    git clone --depth 1 --branch <ref> --filter=blob:none --sparse <url> deps/<name>

and then feeds the `paths` array of `tools/source-lock.json` straight to

    git sparse-checkout add <paths...>

Two things about that array make a fresh fetch impossible:

  1. entries carry a leading slash ("/include/") ->
         fatal: specify directories rather than patterns (no leading slash)
  2. some entries name single files ("net/core/skbuff.c") ->
         fatal: 'net/core/skbuff.c' is not a directory

`fix-ath12k-sparse-paths.py` handles both: it strips the slashes and moves the
file entries into a `files` list. This script teaches fetch-sources.py to stage
that list. The obvious implementation

    git checkout <commit> -- <file>

does NOT work on this clone shape (shallow + blob-filtered + sparse):

    error: pathspec 'net/core/skbuff.c' did not match any file(s) known to git

`git sparse-checkout add --skip-checks <file>` does work: the checkout
machinery fetches the missing blob on demand. Verified against
linux v7.0.14 on git.kernel.org.

This script tolerates three starting states, so it is safe to run twice:
  * the pristine upstream file           -> rewrite the sparse-checkout call
  * a file already carrying this change  -> no-op
  * a file carrying the earlier
    `git checkout <commit> -- <file>`
    attempt                              -> replace that loop

Usage:
    python patch-fetch-sources.py <Ath12kWifi checkout>
"""
import pathlib
import sys

SCRIPT = 'tools/fetch-sources.py'

MARKER = '# single files: a cone-free sparse checkout cannot express them'

ORIGINAL = """    if not check_only:
        subprocess.run(["git", "-C", str(directory), "sparse-checkout", "add", *source["paths"]], check=True)"""

REPLACEMENT = """    if not check_only:
        # Directories and files need different calls. `sparse-checkout add` takes
        # directories only, and `git checkout <commit> -- <file>` cannot resolve a
        # path the sparse cone excludes on a --depth 1 --filter=blob:none clone
        # ("pathspec did not match any file(s) known to git"). --skip-checks is the
        # supported way to include single files; it fetches the blob on demand.
        # single files: a cone-free sparse checkout cannot express them
        if source["paths"]:
            subprocess.run(["git", "-C", str(directory), "sparse-checkout", "add", *source["paths"]],
                           check=True)
        files = source.get("files", [])
        if files:
            subprocess.run(["git", "-C", str(directory), "sparse-checkout", "add",
                            "--skip-checks", *files], check=True)"""

# The intermediate shape produced by the previous revision of this script.
INTERMEDIATE = """    if not check_only:
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

    if MARKER in text:
        print(f'{SCRIPT}: already carries the --skip-checks staging')
        return 0

    for old, label in ((INTERMEDIATE, 'the earlier per-file checkout loop'),
                       (ORIGINAL, 'the upstream sparse-checkout call')):
        if old in text:
            target.write_text(text.replace(old, REPLACEMENT, 1))
            print(f'{SCRIPT}: replaced {label}; single files now use --skip-checks')
            return 0

    raise SystemExit(f'{SCRIPT}: unrecognised content; neither the upstream call nor '
                     f'the earlier loop was found')


if __name__ == '__main__':
    sys.exit(main())
