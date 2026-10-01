import os

import pytest

from meshtastic_sf.config import load_config


@pytest.mark.skipif(os.name == "nt", reason="Windows uses ACLs, not POSIX mode bits")
def test_linux_rejects_public_or_group_writable_password_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[admin]\npassword="synthetic-test-password"\n')
    for mode in (0o644, 0o666, 0o660):
        path.chmod(mode)
        with pytest.raises(ValueError, match="permissions"):
            load_config(str(path))
    for mode in (0o600, 0o640):
        path.chmod(mode)
        assert load_config(str(path)).port == 18765
