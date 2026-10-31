from ha_yas105.config import SystemConfig


def test_set_defaults_creates_config_file(isolated_system_config):
    assert SystemConfig.setDefaults() is True

    config_path = isolated_system_config / "config" / "config.yaml"
    assert config_path.exists()
    assert SystemConfig.config == {"settings": {"test": True}}


def test_load_from_config_file_creates_defaults_when_missing(isolated_system_config):
    assert SystemConfig.loadFromConfigFile() is True
    assert (isolated_system_config / "config" / "config.yaml").exists()
    assert SystemConfig.TEST is True


def test_add_missing_config_parameters_fills_gaps(isolated_system_config):
    loaded = SystemConfig.addMissingConfigParameters({"settings": {}})

    assert loaded is not None
    assert loaded["settings"]["test"] is True
    assert (isolated_system_config / "config" / "config.yaml").exists()


def test_add_missing_config_parameters_preserves_existing_values(
    isolated_system_config,
):
    loaded = SystemConfig.addMissingConfigParameters({"settings": {"test": False}})

    assert loaded is not None
    assert loaded["settings"]["test"] is False
    assert SystemConfig.config == {}


def test_load_from_config_file_fails_on_invalid_yaml(isolated_system_config):
    config_path = isolated_system_config / "config" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("settings: [unclosed\n")

    assert SystemConfig.loadFromConfigFile() is False
