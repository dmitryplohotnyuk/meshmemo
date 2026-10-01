# GitHub publication checklist

The public source repository is
[dmitryplohotnyuk/meshmemo](https://github.com/dmitryplohotnyuk/meshmemo).
MeshMemo remains **alpha / preview**; source publication is not a stable release
or a PyPI publication. The default overview is English, with [a Russian version](../README.ru.md).
The owner selected GPL-3.0-only and private vulnerability reporting is enabled.

## Before publication

- [x] Select GPL-3.0-only, add LICENSE and update project notices. Preserve upstream notices.
- [ ] Review source, dated research and synthetic fixtures for private information.
- [ ] Run the checks below on the final source.
- [x] Configure private vulnerability reporting and link it from SECURITY.md.
- [ ] Review the exact staged diff or source ZIP before uploading.
- [ ] Label the project alpha/preview. Keep phone/radio, whole-host reboot and soak limitations visible.
- [x] Add actual repository URLs to project metadata and configure the reporting channel.

The original working DOCX, databases, flash backups, build trees, virtualenv,
captures and logs belong in private local storage. .gitignore does not remove a
file already tracked; the release check also rejects tracked paths outside its
explicit publication set.

## Checks

```sh
python -m pytest
node --test tests/ui/i18n.test.cjs
python scripts/release-check.py --require-license
python -m build
python -m pip check
```

Run the native harness as described in [CONTRIBUTING](../CONTRIBUTING.md), inspect
both wheel and sdist, and test the installed wheel from a directory outside the
source tree using scripts/smoke-installed.py. CI includes this installation check.
Use a separate environment for the advisory scanner:

```sh
python -m pip install pip-audit==2.10.1
python -m pip_audit -r requirements/constraints.txt --no-deps --disable-pip
```

This scans the recorded runtime versions, not all possible environments or build
dependencies. Re-resolve and audit the actual target deployment too.

## Reviewable source bundle

```sh
python scripts/release-check.py --require-license --output dist/meshmemo-source.zip
```

The script includes only declared source directories/root files and writes a
SHA-256 manifest. It refuses to overwrite an existing ZIP. Review the ZIP even
after the check passes: the scanner recognizes only a few high-confidence secret
patterns. Without --require-license it permits a **private preliminary bundle**
and prints the unresolved license gate.

## Create the repository after review

From a clean extracted source bundle, remove only its generated SOURCE_MANIFEST.json
before Git staging (the manifest is bundle metadata, not source). Initialize Git,
stage the explicit source set, review it, then commit:

```sh
git init -b main
git add README.md README.ru.md CONTRIBUTING.md SECURITY.md CHANGELOG.md LICENSE THIRD_PARTY_NOTICES.md pyproject.toml .gitignore .gitattributes .editorconfig .github src tests scripts firmware docs deploy requirements
git diff --cached --stat
git diff --cached
python scripts/release-check.py --require-license
git commit -m "Initial MeshMemo alpha source"
```

Create the GitHub repository under the intended owner only after this review;
set its remote and push using that repository's actual URL. No owner/remote is
assumed here. Enable Actions and private vulnerability reporting, verify the first
CI run, and require checks/review on the default branch as appropriate. Dependency
update PRs are configured weekly. Tag a release only from the reviewed commit.

A source publication is not production acceptance. Track remaining work in
[current status](implementation-status.md) and [hardware acceptance](hardware-acceptance.md).
