import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def release(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts/release-check.py"
    spec = importlib.util.spec_from_file_location("release_check", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


def test_local_private_data_is_not_a_publication_input(release):
    for name in ("data/archive.db", ".build/firmware.bin", ".venv/secret.txt",
                 "dist/old.zip", "docs/guide.md", "README.md", "src/__pycache__/a.pyc"):
        path = release.ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic", encoding="utf-8")
    assert {p.relative_to(release.ROOT).as_posix() for p in release.public_files()} == {"docs/guide.md", "README.md"}


def test_unexpected_binary_in_public_directory_fails(release):
    (release.ROOT / "docs").mkdir()
    (release.ROOT / "docs/private.docx").write_bytes(b"synthetic")
    with pytest.raises(ValueError, match="Unexpected publication file"):
        release.public_files()


def test_secret_and_private_link_report_paths_not_values(release):
    secret = "gh" + "p_" + "a" * 40
    path = release.ROOT / "README.md"
    path.write_text(secret + "\n[backup](data/private.db)", encoding="utf-8")
    errors = release.check([path])
    assert len(errors) == 2
    assert "README.md" in errors[0]
    assert secret not in "".join(errors)


def test_license_is_required_for_publication_mode(release):
    assert release.check([], require_license=False) == []
    assert "LICENSE" in release.check([], require_license=True)[0]
