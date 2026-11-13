#!/usr/bin/env python3
"""Apply the pinned Mesa series and validate it against the pinned commit.

This is the step that stopped package #10: git apply with the whole series used
--unsafe-paths, which let the three file-creating patches through but made the
reverse-apply check in mesa_patch_identity.py fail. Here the flag is used only
where the patch really creates a file, so the tree stays byte-exact.
"""
import importlib.util
import json
import pathlib
import subprocess
import sys


def main():
    root = pathlib.Path.cwd()
    sys.path.insert(0, str(root / "scripts"))

    spec = importlib.util.spec_from_file_location(
        "bbr", root / "scripts/build-boot-runtime.py"
    )
    bbr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bbr)

    pins = json.loads((root / "scripts/data/adreno-compiler-inputs.json").read_text())
    mesa = root / ".cache/mesa-work"
    print("pinned mesa:", pins["mesa"], flush=True)

    fresh = bbr.checkout(mesa, pins["mesa"])
    print("fresh checkout:", fresh, flush=True)

    if fresh:
        for patch in pins["patches"]:
            text = (root / patch).read_text()
            create = "\n--- /dev/null" in text
            argv = ["git", "-C", str(mesa), "apply"]
            if create:
                argv.append("--unsafe-paths")
            argv.append(str(root / patch))
            result = subprocess.run(argv, capture_output=True, text=True)
            name = pathlib.Path(patch).name
            if result.returncode:
                print("FAILED to apply", name, "create=%s" % create, flush=True)
                print(result.stderr[:3000], flush=True)
                return 1
            print("applied", name, "create=%s" % create, flush=True)

    print("--- validating against the pinned commit ---", flush=True)
    from mesa_patch_identity import validate_recorded_patches

    validate_recorded_patches(root, mesa, pins)
    print("PASS: the patched tree reconstructs the pinned commit", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
