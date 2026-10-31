# Static class for configuration parameters

import logging
import os
import tomllib

import yaml

logger_mp = logging.getLogger(__name__)


class IndentedSafeDumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, indentless=False)


class SystemConfig:
    CONFIG_FILE_PATH = "./config/config.yaml"

    _TEST_DEFAULT = True

    TEST = _TEST_DEFAULT

    config = {}

    VERSION = "0.1.0"

    @staticmethod
    def generateDefaultConfig() -> dict:
        # Set the config file structure with default values as a dictionary
        return {
            "settings": {
                "test": SystemConfig._TEST_DEFAULT,
            },
        }

    @staticmethod
    def setDefaults() -> bool:
        try:
            # Ensure the directory exists before writing
            os.makedirs(os.path.dirname(SystemConfig.CONFIG_FILE_PATH), exist_ok=True)
            config = SystemConfig.generateDefaultConfig()

            with open(SystemConfig.CONFIG_FILE_PATH, "w") as configfile:
                yaml.safe_dump(
                    config,
                    configfile,
                    indent=4,
                    default_flow_style=False,
                )

            # Attempt to load
            SystemConfig.loadFromConfigFile()
            logger_mp.info("[Config] Default configuration file created successfully.")
            return True
        except Exception as e:
            logger_mp.error(f"[Config] Error occurred while writing config file: {e}")
            return False

    @staticmethod
    def loadFromConfigFile() -> bool:

        config = SystemConfig.getConfigFromFile(SystemConfig.CONFIG_FILE_PATH)

        if config is None:
            return False

        updatedConfig = SystemConfig.addMissingConfigParameters(config)

        if updatedConfig is None:
            return False

        SystemConfig.config = updatedConfig

        try:
            SystemConfig.TEST = SystemConfig.config["settings"]["test"]

            logger_mp.info("[Config] Configuration loaded successfully.")
            return True
        except Exception as e:
            logger_mp.error(f"[Config] Error occurred while loading configuration: {e}")
            return False

    @staticmethod
    def getConfigFromFile(path: str) -> dict | None:
        # Check if config file exists, if not create it with defaults
        if not os.path.exists(SystemConfig.CONFIG_FILE_PATH):
            logger_mp.warning(
                f"[Config] Configuration file {SystemConfig.CONFIG_FILE_PATH} not found. Creating default configuration."
            )
            if not SystemConfig.setDefaults():
                logger_mp.error("[Config] Failed to create default configuration file.")
                return None

        try:
            with open(path) as configfile:
                config = yaml.safe_load(configfile)
                return config if config is not None else {}
        except Exception as e:
            logger_mp.error(f"[Config] Error occurred while loading configuration: {e}")
            return None

    @staticmethod
    def addMissingConfigParameters(
        config: dict,
    ) -> dict | None:
        # Compares the parameters in the config file with the expected default parameters and adds them if they are missing
        # If there's a change, then save to file
        defaultConfig = SystemConfig.generateDefaultConfig()
        changed = False
        try:
            for section, options in defaultConfig.items():
                # Ensure section exists in config file
                if section not in config:
                    config[section] = options
                    changed = True
                else:
                    for option, value in options.items():
                        if option not in config[section]:
                            config[section][option] = value
                            changed = True
        except Exception as e:
            logger_mp.error(
                f"[Config] Error occurred while adding missing parameters: {e}"
            )
            return None

        if changed:
            try:
                os.makedirs(
                    os.path.dirname(SystemConfig.CONFIG_FILE_PATH), exist_ok=True
                )
                with open(SystemConfig.CONFIG_FILE_PATH, "w") as configfile:
                    yaml.safe_dump(
                        config, configfile, default_flow_style=False, indent=4
                    )
            except Exception as e:
                logger_mp.error(
                    f"[Config] Error occurred while writing config file: {e}"
                )
                return None
            logger_mp.info(
                "[Config] Configuration file updated with missing parameters."
            )

        return config

    # 1. Create a custom Dumper to force proper list indentation
    @staticmethod
    def loadVersion():
        try:
            SystemConfig.VERSION = tomllib.load(open("pyproject.toml", "rb"))[
                "project"
            ]["version"]
        except Exception as e:
            logger_mp.error(f"[Config] Error occurred while loading configuration: {e}")
            SystemConfig.VERSION = "0.1.0"
            return None
