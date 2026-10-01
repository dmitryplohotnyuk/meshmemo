"""Check public source files and optionally create a reviewed-source ZIP.

This is a narrow publication guard, not a full secret scanner or legal review.
Local data/build directories are never traversed for bundle creation.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {".github", "src", "tests", "scripts", "firmware", "docs", "deploy", "requirements"}
FILES = {"README.md", "README.ru.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", "LICENSE",
         "THIRD_PARTY_NOTICES.md", "pyproject.toml", ".gitignore", ".gitattributes", ".editorconfig"}
EXTENSIONS = {".py", ".md", ".json", ".js", ".cjs", ".css", ".html", ".svg", ".proto",
              ".patch", ".cpp", ".h", ".ps1", ".service", ".txt", ".yml", ".yaml", ".toml"}
IGNORED = {"__pycache__", ".pytest_cache"}
SENSITIVE = re.compile(
    r"-----BEGIN " + r"(?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    r"|gh[pousr]_" + r"[A-Za-z0-9]{36,}"
    r"|github_pat_" + r"[A-Za-z0-9_]{30,}"
    r"|https?://meshtastic\.org/e/" + r"#[A-Za-z0-9_-]{16,}"
)


def public_files():
    found = []
    for name in sorted(FILES):
        path = ROOT / name
        if path.exists():
            found.append(path)
    for name in sorted(DIRECTORIES):
        directory = ROOT / name
        if directory.is_symlink():
            raise ValueError(f"Publication directory is a symlink: {name}")
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(ROOT)
            if any(part in IGNORED for part in relative.parts) or path.suffix == ".pyc":
                continue
            if path.is_symlink():
                raise ValueError(f"Publication symlink: {relative}")
            if path.is_file():
                if path.name in {"config.toml", "meshmemo.toml"}:
                    raise ValueError(f"Private configuration in publication directory: {relative}")
                if path.suffix not in EXTENSIONS:
                    raise ValueError(f"Unexpected publication file: {relative}")
                found.append(path)
    return found


def check(paths, require_license=False):
    errors = []
    names = {path.relative_to(ROOT).as_posix() for path in paths}
    for path in paths:
        name = path.relative_to(ROOT).as_posix()
        if path.is_symlink():
            errors.append(f"Publication symlink: {name}")
            continue
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeError:
            errors.append(f"Non-text publication file: {name}")
            continue
        if SENSITIVE.search(content):
            errors.append(f"Possible credential/channel URL: {name} (value suppressed)")
        if path.suffix == ".md":
            for link in re.findall(r"\]\(([^\s)]+)\)", content):
                if re.match(r"^[a-z]+:", link, re.I) or link.startswith("#"):
                    continue
                target = (path.parent / unquote(link.split("#")[0])).resolve()
                try:
                    target_name = target.relative_to(ROOT).as_posix()
                except ValueError:
                    target_name = ""
                if target_name not in names:
                    errors.append(f"Missing/non-public link in {name}: {link}")
    if (ROOT / ".git").exists():
        result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
        for name in result.stdout.decode("utf-8").split("\0"):
            if name and name not in names:
                errors.append(f"Tracked file outside publication set: {name}")
    if not (ROOT / "LICENSE").is_file():
        message = "Project LICENSE is missing; owner decision is required before publication."
        if require_license:
            errors.append(message)
        else:
            print("PUBLICATION GATE: " + message)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-license", action="store_true")
    parser.add_argument("--output", type=Path, help="Create a new ZIP; never overwrite an existing file")
    args = parser.parse_args()
    try:
        paths = public_files()
        errors = check(paths, args.require_license)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Checked {len(paths)} public source files; no matching credential signatures or broken local Markdown links.")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        manifest = {}
        with zipfile.ZipFile(args.output, "x", zipfile.ZIP_DEFLATED) as bundle:
            for path in paths:
                name = path.relative_to(ROOT).as_posix()
                payload = path.read_bytes()
                bundle.writestr("meshmemo/" + name, payload)
                manifest[name] = hashlib.sha256(payload).hexdigest()
            bundle.writestr("meshmemo/SOURCE_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
        print(f"Created {args.output} ({len(paths)} files plus SHA-256 manifest). Review before publishing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
