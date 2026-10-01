"""Create a fresh pinned checkout and apply an explicitly selected board profile."""

import argparse
from pathlib import Path
import subprocess
import shutil

BASE = "54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb"
PROTOBUF_BASE = "6b1ded439633cd03d4af85b44231b91d1d106278"
ROOT = Path(__file__).resolve().parents[1]


def git(*args, cwd=None, capture=False):
    return subprocess.run(["git", *map(str, args)], cwd=cwd, check=True,
                          text=True, stdout=subprocess.PIPE if capture else None).stdout


def clone(source, destination, commit):
    source_path = Path(source)
    settings = ["-c", f"safe.directory={source_path.resolve().as_posix()}"] if source_path.exists() else []
    git(*settings, "clone", "--no-hardlinks", "--no-checkout", source, destination)
    git("checkout", "--detach", commit, cwd=destination)
    assert git("rev-parse", "HEAD", cwd=destination, capture=True).strip() == commit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=["inherited-ua22"])
    parser.add_argument("--destination", type=Path, default=ROOT / ".build" / "firmware")
    parser.add_argument("--firmware-source", default="https://github.com/meshtastic/firmware.git")
    parser.add_argument("--protobuf-source", default="https://github.com/meshtastic/protobufs.git")
    parser.add_argument("--replay", action="store_true", help="Prepare experimental fresh-ID replay profile 1 (never flashes)")
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.exists():
        parser.error("Destination exists; choose a new directory. Existing work is never replaced.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    clone(args.firmware_source, destination, BASE)
    clone(args.protobuf_source, destination / "protobufs", PROTOBUF_BASE)
    for working_dir, patch in [
        (destination, ROOT / "firmware/patches/0001-inherited-ua22-cyrillic-windows.patch"),
        (destination / "protobufs", ROOT / "firmware/protocol/0001-usb-sf-field.patch"),
        (destination, ROOT / "firmware/patches/0002-usb-diagnostics.patch"),
    ]:
        git("apply", "--check", patch, cwd=working_dir)
        git("apply", patch, cwd=working_dir)
    if args.replay:
        patch = ROOT / "firmware/patches/0003-usb-replay.patch"
        git("apply", "--check", patch, cwd=destination)
        git("apply", patch, cwd=destination)
        poll_patch = ROOT / 'firmware/patches/0004-usb-poll.patch'
        git('apply','--check',poll_patch,cwd=destination)
        git('apply',poll_patch,cwd=destination)
        screen_patch = ROOT / 'firmware/patches/0005-usb-screen-timeout.patch'
        git('apply','--check',screen_patch,cwd=destination)
        git('apply',screen_patch,cwd=destination)
        catalog_patch = ROOT / 'firmware/patches/0006-server-channels.patch'
        git('apply', '--check', catalog_patch, cwd=destination)
        git('apply', catalog_patch, cwd=destination)
        for source in (ROOT / "firmware/replay").glob("UsbSf*.*"):
            shutil.copy2(source, destination / "src/mesh" / source.name)
    print(f"Prepared profile {1 if args.replay else 0} at {destination}. No device was accessed.")


if __name__ == "__main__":
    main()
