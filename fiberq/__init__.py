"""
FiberQ - QGIS Plugin for Fiber Optic Network Design

This plugin provides tools for designing and documenting fiber optic networks
including route planning, cable laying, element placement, and documentation.

Supported QGIS Versions: 3.22 LTR - 4.x (Qt5 and Qt6)

Version: 1.2.3 (QGIS Repo)
"""

# Minimum supported QGIS version
MINIMUM_QGIS_VERSION = 32200  # 3.22.0
MINIMUM_QGIS_VERSION_STR = "3.22"


class FiberQVersionError(Exception):
    """Raised when QGIS version is incompatible with FiberQ."""
    pass


def check_qgis_version():
    """
    Verify QGIS version meets minimum requirements.

    Returns:
        tuple: (version_int, version_str) if compatible

    Raises:
        FiberQVersionError: If QGIS version is too old
    """
    try:
        from qgis.core import Qgis
        version_int = Qgis.QGIS_VERSION_INT
        version_str = Qgis.QGIS_VERSION
    except ImportError:
        raise FiberQVersionError(
            "Could not detect QGIS version. FiberQ requires QGIS 3.22 or later."
        )

    if version_int < MINIMUM_QGIS_VERSION:
        raise FiberQVersionError(
            f"FiberQ requires QGIS {MINIMUM_QGIS_VERSION_STR} or later. "
            f"Current version: {version_str}"
        )

    return version_int, version_str


def _show_version_error(iface, error_msg):
    """Display version error to user."""
    try:
        from qgis.PyQt.QtWidgets import QMessageBox
        QMessageBox.critical(
            iface.mainWindow() if iface else None,
            "FiberQ - Version Error",
            error_msg
        )
    except Exception:
        # If we can't show a dialog, at least print to console
        print(f"FiberQ Error: {error_msg}")


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """
    Load the FiberQ plugin class.

    This function is called by QGIS when loading the plugin.

    Args:
        iface: A QGIS interface instance

    Returns:
        FiberQPlugin instance or a stub if version check fails
    """
    # Check QGIS version first
    try:
        version_int, version_str = check_qgis_version()
    except FiberQVersionError as e:
        _show_version_error(iface, str(e))
        # Return a stub plugin that does nothing
        return _FiberQStub(iface, str(e))

    # Log version info for debugging
    try:
        from qgis.core import QgsMessageLog, Qgis
        QgsMessageLog.logMessage(
            f"FiberQ loading on QGIS {version_str}",
            "FiberQ",
            Qgis.MessageLevel.Info
        )
    except Exception:
        pass

    # Import and return the actual plugin
    from .main_plugin import FiberQPlugin
    return FiberQPlugin(iface)


class _FiberQStub:
    """
    Stub plugin class used when QGIS version check fails.

    This prevents crashes by providing empty implementations of
    required plugin methods.
    """

    def __init__(self, iface, error_msg):
        self.iface = iface
        self.error_msg = error_msg

    def initGui(self):
        """Initialize GUI (no-op for stub)."""
        pass

    def unload(self):
        """Unload plugin (no-op for stub)."""
        pass


# =============================================================================
# PACKAGE INFO
# =============================================================================

__version__ = "1.3.0"
__author__ = "Vladimir Vukovic"
__email__ = "vukovicvl@fiberq.net"
__license__ = "GPL-3.0-or-later"

__all__ = [
    'classFactory',
    'check_qgis_version',
    'FiberQVersionError',
    'MINIMUM_QGIS_VERSION',
    'MINIMUM_QGIS_VERSION_STR',
]
