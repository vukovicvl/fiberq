"""
FiberQ v2 - Configuration Manager Module

This module handles all configuration loading and saving for the FiberQ plugin,
including reading config.ini, managing QSettings, and handling project-level settings.
"""

import os
import configparser
from typing import Dict, Optional
from dataclasses import dataclass, field

from qgis.PyQt.QtCore import QSettings
from qgis.core import QgsProject

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


# =============================================================================
# CONFIGURATION DATA CLASSES
# =============================================================================

@dataclass
class WebConfig:
    """Web-related configuration settings."""
    viewer_url: str = ""
    support_url: str = ""


@dataclass
class LayerConfig:
    """Layer naming configuration."""
    # Route layer
    routes_layer_name: str = "Route"
    routes_table: str = "ftth_routes"

    # Pole layer
    poles_layer_name: str = "Poles"
    poles_table: str = "ftth_poles"

    # Manhole layer
    manholes_layer_name: str = "Manholes"
    manholes_table: str = "ftth_manholes"

    # Cable layers
    aerial_cables_layer_name: str = "Aerial_cables"
    aerial_cables_table: str = "ftth_aerial_cables"
    underground_cables_layer_name: str = "Underground_cables"
    underground_cables_table: str = "ftth_underground_cables"

    # Duct layers
    pe_ducts_layer_name: str = "PE_ducts"
    transition_ducts_layer_name: str = "Transition_ducts"
    ducts_table: str = "ftth_ducts"

    # Element layers
    joint_closures_layer_name: str = "Joint_closures"
    joint_closures_table: str = "ftth_joint_closures"
    optical_slack_layer_name: str = "Optical_slack"
    optical_slack_table: str = "ftth_slack"
    fiber_breaks_layer_name: str = "Fiber_breaks"
    fiber_breaks_table: str = "ftth_breaks"


@dataclass
class PluginConfig:
    """Complete plugin configuration."""
    web: WebConfig = field(default_factory=WebConfig)
    layers: LayerConfig = field(default_factory=LayerConfig)

    # Plugin info (from metadata.txt)
    name: str = "FiberQ"
    version: str = "2.0"
    author: str = ""
    email: str = ""
    about: str = ""


# =============================================================================
# CONFIGURATION MANAGER
# =============================================================================

class ConfigManager:
    """
    Manages all configuration for the FiberQ plugin.

    Handles:
    - Reading config.ini file
    - Reading metadata.txt
    - QSettings for user preferences
    - Project-level settings via QgsProject
    """

    # QSettings keys
    SETTINGS_ORG = "FiberQ"
    SETTINGS_APP = "FiberQ"

    # Settings keys
    KEY_LANGUAGE = "FiberQ/lang"
    KEY_PRO_ENABLED = "pro_enabled"
    KEY_COLOR_CATALOGS = "ColorCatalogs/catalogs_v1"

    # Pro license master key
    PRO_MASTER_KEY = "FIBERQ-PRO-2025"

    def __init__(self, plugin_dir: Optional[str] = None):
        """
        Initialize the configuration manager.

        Args:
            plugin_dir: Path to plugin directory (auto-detected if None)
        """
        if plugin_dir is None:
            plugin_dir = os.path.dirname(os.path.dirname(__file__))

        self._plugin_dir = plugin_dir
        self._config: Optional[PluginConfig] = None
        self._config_parser: Optional[configparser.ConfigParser] = None

    @property
    def plugin_dir(self) -> str:
        """Get the plugin directory path."""
        return self._plugin_dir

    @property
    def config_file_path(self) -> str:
        """Get the path to config.ini."""
        return os.path.join(self._plugin_dir, 'config.ini')

    @property
    def metadata_file_path(self) -> str:
        """Get the path to metadata.txt."""
        return os.path.join(self._plugin_dir, 'metadata.txt')

    # -------------------------------------------------------------------------
    # Config file loading
    # -------------------------------------------------------------------------

    def load_config(self, force_reload: bool = False) -> PluginConfig:
        """
        Load configuration from config.ini and metadata.txt.

        Args:
            force_reload: Force reload even if already loaded

        Returns:
            PluginConfig object with all settings
        """
        if self._config is not None and not force_reload:
            return self._config

        config = PluginConfig()

        # Load metadata.txt
        metadata = self._read_metadata()
        config.name = metadata.get('name', 'FiberQ')
        config.version = metadata.get('version', '2.0')
        config.author = metadata.get('author', '')
        config.email = metadata.get('email', '')
        config.about = metadata.get('about', '')

        # Load config.ini
        self._load_config_ini()

        if self._config_parser is not None:
            # Web settings
            config.web.viewer_url = self._get_ini_value('web', 'viewer_url', '')
            config.web.support_url = self._get_ini_value('web', 'support_url', '')

            # Layer settings (with backward compatibility for Serbian names)
            config.layers.routes_layer_name = self._get_ini_value(
                'layers', 'routes_layer_name',
                self._get_ini_value('layers', 'trase_layer_name', 'Route')
            )
            config.layers.poles_layer_name = self._get_ini_value(
                'layers', 'poles_layer_name',
                self._get_ini_value('layers', 'stubovi_layer_name', 'Poles')
            )
            config.layers.manholes_layer_name = self._get_ini_value(
                'layers', 'manholes_layer_name',
                self._get_ini_value('layers', 'okna_layer_name', 'Manholes')
            )

        self._config = config
        return config

    def _load_config_ini(self) -> None:
        """Load the config.ini file."""
        try:
            if os.path.exists(self.config_file_path):
                parser = configparser.ConfigParser()
                parser.read(self.config_file_path, encoding='utf-8')
                self._config_parser = parser
        except Exception as e:
            self._config_parser = None

    def _get_ini_value(
        self,
        section: str,
        key: str,
        default: str = ""
    ) -> str:
        """
        Get a value from config.ini.

        Args:
            section: Config section name
            key: Config key name
            default: Default value if not found

        Returns:
            Config value or default
        """
        if self._config_parser is None:
            return default

        try:
            if (self._config_parser.has_section(section) and
                self._config_parser.has_option(section, key)):
                return self._config_parser.get(section, key)
        except Exception as e:
            logger.debug(f"Error in ConfigManager._get_ini_value: {e}")

        return default

    def _read_metadata(self) -> Dict[str, str]:
        """
        Read metadata.txt file.

        Returns:
            Dictionary of metadata values
        """
        metadata = {}

        try:
            if os.path.exists(self.metadata_file_path):
                parser = configparser.ConfigParser()
                parser.read(self.metadata_file_path, encoding='utf-8')

                if parser.has_section('general'):
                    metadata = dict(parser.items('general'))
        except Exception as e:
            logger.debug(f"Error in ConfigManager._read_metadata: {e}")

        return metadata

    # -------------------------------------------------------------------------
    # User preferences (QSettings)
    # -------------------------------------------------------------------------

    def get_language(self) -> str:
        """
        Get the current UI language.

        Returns:
            Language code ('en' or 'sr')
        """
        try:
            return QSettings().value(self.KEY_LANGUAGE, "en")
        except Exception as e:
            return "en"

    def set_language(self, lang: str) -> None:
        """
        Set the UI language.

        Args:
            lang: Language code ('en' or 'sr')
        """
        try:
            QSettings().setValue(self.KEY_LANGUAGE, lang)
        except Exception as e:
            logger.debug(f"Error in ConfigManager.set_language: {e}")

    # -------------------------------------------------------------------------
    # Pro license management
    # -------------------------------------------------------------------------

    def is_pro_enabled(self) -> bool:
        """
        Check if Pro features are enabled.

        Returns:
            True if Pro is enabled
        """
        try:
            settings = QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)
            return settings.value(self.KEY_PRO_ENABLED, False, type=bool)
        except Exception as e:
            return False

    def set_pro_enabled(self, enabled: bool) -> None:
        """
        Set Pro enabled status.

        Args:
            enabled: Whether Pro should be enabled
        """
        try:
            settings = QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)
            settings.setValue(self.KEY_PRO_ENABLED, bool(enabled))
        except Exception as e:
            logger.debug(f"Error in ConfigManager.set_pro_enabled: {e}")

    def validate_pro_key(self, key: str) -> bool:
        """
        Validate a Pro license key.

        Args:
            key: License key to validate

        Returns:
            True if key is valid
        """
        if not isinstance(key, str):
            return False

        try:
            cleaned_key = key.strip().upper()
            return cleaned_key == self.PRO_MASTER_KEY
        except Exception as e:
            return False

    # -------------------------------------------------------------------------
    # Project settings
    # -------------------------------------------------------------------------

    def get_project_setting(
        self,
        key: str,
        default: str = "",
        scope: str = "StuboviPlugin"
    ) -> str:
        """
        Get a project-level setting.

        Args:
            key: Setting key
            default: Default value if not found
            scope: Settings scope/group name

        Returns:
            Setting value
        """
        try:
            project = QgsProject.instance()
            value, success = project.readEntry(scope, key, default)
            return value if success else default
        except Exception as e:
            return default

    def set_project_setting(
        self,
        key: str,
        value: str,
        scope: str = "StuboviPlugin"
    ) -> bool:
        """
        Set a project-level setting.

        Args:
            key: Setting key
            value: Value to store
            scope: Settings scope/group name

        Returns:
            True if successful
        """
        try:
            project = QgsProject.instance()
            return project.writeEntry(scope, key, value)
        except Exception as e:
            return False


# =============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# =============================================================================

# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """
    Get the global ConfigManager instance.

    Returns:
        ConfigManager instance
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def get_config() -> PluginConfig:
    """
    Get the current plugin configuration.

    Returns:
        PluginConfig object
    """
    return get_config_manager().load_config()


def get_language() -> str:
    """Get the current UI language."""
    return get_config_manager().get_language()


def set_language(lang: str) -> None:
    """Set the UI language."""
    get_config_manager().set_language(lang)


def is_pro_enabled() -> bool:
    """Check if Pro features are enabled."""
    return get_config_manager().is_pro_enabled()


def validate_pro_key(key: str) -> bool:
    """Validate a Pro license key."""
    return get_config_manager().validate_pro_key(key)
