from pathlib import Path
import tomllib

import pytest

from meshtastic_sf import __version__
from meshtastic_sf.cli import main


def test_cli_module_and_package_versions_agree(monkeypatch, capsys):
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    assert __version__ == project["project"]["version"]
    monkeypatch.setattr("sys.argv", ["meshtastic-sf-server", "--version"])
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 0
    assert capsys.readouterr().out.strip() == __version__
