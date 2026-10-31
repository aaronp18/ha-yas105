import pytest

from ha_yas105.config import SystemConfig


@pytest.fixture
def isolated_system_config(tmp_path, monkeypatch):
    """Point config paths at a temp dir so tests never touch the repo.

    ``SystemConfig`` uses process-wide class attributes, so every attribute a
    test may mutate is patched here and restored automatically by pytest.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        SystemConfig, "CONFIG_FILE_PATH", str(tmp_path / "config" / "config.yaml")
    )
    monkeypatch.setattr(SystemConfig, "config", {})
    return tmp_path
