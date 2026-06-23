"""
FiberQ v2 - License Manager Module

This module handles FiberQ Pro license validation and management.
Pro features include Preview Map and Publish to PostGIS.

Phase 1.2 Refactoring: Extracted from main_plugin.py for better modularity.
"""

from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QMessageBox, QInputDialog, QLineEdit

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


# =============================================================================
# LICENSE CONFIGURATION
# =============================================================================

# QSettings organization/app names for storing license state
_FIBERQ_PRO_SETTINGS_ORG = "FiberQ"
_FIBERQ_PRO_SETTINGS_APP = "FiberQ"
_FIBERQ_PRO_ENABLED_KEY = "pro_enabled"

# Master license key - change this to rotate the shared key
_FIBERQ_PRO_MASTER_KEY = "FIBERQ-PRO-2025"


# =============================================================================
# LICENSE STATE FUNCTIONS
# =============================================================================

def _fiberq_is_pro_enabled() -> bool:
    """
    Check if FiberQ Pro is enabled on this computer.

    Returns:
        True if Pro is enabled, False otherwise
    """
    try:
        s = QSettings(_FIBERQ_PRO_SETTINGS_ORG, _FIBERQ_PRO_SETTINGS_APP)
        return s.value(_FIBERQ_PRO_ENABLED_KEY, False, type=bool)
    except Exception:
        return False


def _fiberq_set_pro_enabled(value: bool) -> None:
    """
    Set the FiberQ Pro enabled state.

    Args:
        value: True to enable Pro, False to disable
    """
    try:
        s = QSettings(_FIBERQ_PRO_SETTINGS_ORG, _FIBERQ_PRO_SETTINGS_APP)
        s.setValue(_FIBERQ_PRO_ENABLED_KEY, bool(value))
    except Exception as e:
        logger.debug(f"Error saving Pro license state: {e}")


def _fiberq_validate_pro_key(key: str) -> bool:
    """
    Validate a FiberQ Pro license key.

    Args:
        key: License key to validate

    Returns:
        True if key is valid, False otherwise
    """
    try:
        if not isinstance(key, str):
            return False
        k = key.strip().upper()
        return k == _FIBERQ_PRO_MASTER_KEY
    except Exception:
        return False


# =============================================================================
# LICENSE CHECK UI
# =============================================================================

def _fiberq_check_pro(iface, feature_label: str = "FiberQ Pro") -> bool:
    """
    Check if Pro is enabled; if not, prompt user for license key.

    This function is called when accessing Pro features (Preview Map,
    Publish to PostGIS). If Pro is already enabled, returns True immediately.
    Otherwise, shows a dialog asking if user wants to enter a license key.

    Args:
        iface: QGIS interface object
        feature_label: Name of the feature being accessed (for display)

    Returns:
        True if Pro is enabled (either already or just activated), False otherwise
    """
    try:
        # Already enabled - return immediately
        if _fiberq_is_pro_enabled():
            return True

        # Ask if user wants to enter a key
        res = QMessageBox.question(
            iface.mainWindow(),
            "FiberQ Pro",
            "Preview Map and Publish to PostGIS are part of FiberQ Pro.\n\n"
            "Do you want to enter a license key now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if res != QMessageBox.StandardButton.Yes:
            return False

        # Get license key from user
        key, ok = QInputDialog.getText(
            iface.mainWindow(),
            "FiberQ Pro",
            "Enter license key:",
            QLineEdit.EchoMode.Normal,
            ""
        )
        if not ok:
            return False

        # Validate and activate
        if _fiberq_validate_pro_key(key):
            _fiberq_set_pro_enabled(True)
            QMessageBox.information(
                iface.mainWindow(),
                "FiberQ Pro",
                "Activated! Pro options are now unlocked on this computer."
            )
            return True
        else:
            QMessageBox.warning(
                iface.mainWindow(),
                "FiberQ Pro",
                "Invalid license key."
            )
            return False

    except Exception:
        return False


# =============================================================================
# CONVENIENCE FUNCTIONS (new API)
# =============================================================================

def is_pro_enabled() -> bool:
    """
    Check if FiberQ Pro is enabled.

    New API - prefer this over _fiberq_is_pro_enabled() in new code.

    Returns:
        True if Pro is enabled
    """
    return _fiberq_is_pro_enabled()


def set_pro_enabled(enabled: bool) -> None:
    """
    Set FiberQ Pro enabled state.

    New API - prefer this over _fiberq_set_pro_enabled() in new code.

    Args:
        enabled: True to enable, False to disable
    """
    _fiberq_set_pro_enabled(enabled)


def validate_license_key(key: str) -> bool:
    """
    Validate a license key.

    New API - prefer this over _fiberq_validate_pro_key() in new code.

    Args:
        key: License key to validate

    Returns:
        True if valid
    """
    return _fiberq_validate_pro_key(key)


def check_pro_access(iface, feature_name: str = "this feature") -> bool:
    """
    Check Pro access and prompt for license if needed.

    New API - prefer this over _fiberq_check_pro() in new code.

    Args:
        iface: QGIS interface
        feature_name: Name of feature being accessed

    Returns:
        True if access granted
    """
    return _fiberq_check_pro(iface, feature_name)


def reset_pro_license() -> None:
    """
    Reset/deactivate the Pro license on this computer.

    Useful for testing or when user wants to re-enter a different key.
    """
    _fiberq_set_pro_enabled(False)


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    # Legacy API (for backward compatibility)
    '_fiberq_is_pro_enabled',
    '_fiberq_set_pro_enabled',
    '_fiberq_validate_pro_key',
    '_fiberq_check_pro',

    # New API
    'is_pro_enabled',
    'set_pro_enabled',
    'validate_license_key',
    'check_pro_access',
    'reset_pro_license',

    # Constants (if needed externally)
    '_FIBERQ_PRO_MASTER_KEY',
]
