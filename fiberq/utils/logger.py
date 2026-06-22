# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""
FiberQ Logging Infrastructure

This module provides a centralized logging system for the FiberQ plugin.
Logs are sent to both the QGIS Message Log panel and optionally to a file.

Configuration via environment variables:
    FIBERQ_LOG_LEVEL: Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                      Default: WARNING
    FIBERQ_LOG_FILE: Set to 'true' to enable file logging
                     Default: false (disabled)

Usage:
    from fiberq.utils.logger import get_logger
    logger = get_logger(__name__)

    logger.debug("Detailed info for debugging")
    logger.info("General information")
    logger.warning("Something unexpected but handled")
    logger.error("Error occurred", exc_info=True)

Quick exception logging:
    from fiberq.utils.logger import log_exception

    try:
        risky_operation()
    except Exception as e:
        log_exception("Failed to perform operation", e)

Enable debug logging (before starting QGIS):
    export FIBERQ_LOG_LEVEL=DEBUG
    export FIBERQ_LOG_FILE=true
    qgis
"""

import logging
import os
from pathlib import Path
from typing import Optional

# Try to import QGIS - may not be available in tests
try:
    from qgis.core import QgsMessageLog, Qgis
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    # Define fallback constants for testing outside QGIS
    class Qgis:
        Info = 0
        Warning = 1
        Critical = 2

# =============================================================================
# Configuration
# =============================================================================

# Log level from environment variable (default: WARNING)
LOG_LEVEL = os.environ.get('FIBERQ_LOG_LEVEL', 'WARNING').upper()

# File logging enabled via environment variable (default: disabled)
LOG_TO_FILE = os.environ.get('FIBERQ_LOG_FILE', '').lower() == 'true'

# Log file path
LOG_FILE_PATH = Path.home() / '.fiberq' / 'fiberq.log'

# Plugin name for QGIS Message Log
PLUGIN_NAME = 'FiberQ'

# =============================================================================
# QGIS Log Handler
# =============================================================================

class QgsLogHandler(logging.Handler):
    """
    Custom logging handler that sends log messages to the QGIS Message Log panel.

    Maps Python logging levels to QGIS message levels:
        DEBUG, INFO → Qgis.MessageLevel.Info
        WARNING → Qgis.MessageLevel.Warning
        ERROR, CRITICAL → Qgis.MessageLevel.Critical
    """

    LEVEL_MAP = {
        logging.DEBUG: Qgis.MessageLevel.Info,
        logging.INFO: Qgis.MessageLevel.Info,
        logging.WARNING: Qgis.MessageLevel.Warning,
        logging.ERROR: Qgis.MessageLevel.Critical,
        logging.CRITICAL: Qgis.MessageLevel.Critical,
    }

    def __init__(self, plugin_name: str = PLUGIN_NAME):
        super().__init__()
        self.plugin_name = plugin_name

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the QGIS Message Log."""
        try:
            msg = self.format(record)
            level = self.LEVEL_MAP.get(record.levelno, Qgis.MessageLevel.Info)

            if QGIS_AVAILABLE:
                QgsMessageLog.logMessage(msg, self.plugin_name, level)
            else:
                # Fallback for testing outside QGIS
                print(f"[{self.plugin_name}] {msg}")

        except Exception:
            self.handleError(record)


# =============================================================================
# Logger Factory
# =============================================================================

# Cache for loggers to avoid duplicate handlers
_loggers: dict = {}


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger for the given module name.

    Args:
        name: The module name, typically __name__

    Returns:
        A configured logging.Logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("Plugin initialized")
        logger.warning("Configuration missing, using defaults")
        logger.error("Failed to load layer", exc_info=True)
    """
    # Return cached logger if already configured
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        # Set log level from environment
        level = getattr(logging, LOG_LEVEL, logging.WARNING)
        logger.setLevel(level)

        # QGIS Message Log handler
        qgs_handler = QgsLogHandler()
        qgs_handler.setFormatter(logging.Formatter(
            '%(name)s - %(levelname)s - %(message)s'
        ))
        qgs_handler.setLevel(level)
        logger.addHandler(qgs_handler)

        # Optional file handler
        if LOG_TO_FILE:
            try:
                LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
                file_handler = logging.FileHandler(LOG_FILE_PATH, encoding='utf-8')
                file_handler.setFormatter(logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                ))
                file_handler.setLevel(level)
                logger.addHandler(file_handler)
            except Exception as e:
                # Can't log to file, but don't crash
                qgs_handler.emit(logging.LogRecord(
                    name=name,
                    level=logging.WARNING,
                    pathname='',
                    lineno=0,
                    msg=f"Failed to setup file logging: {e}",
                    args=(),
                    exc_info=None
                ))

        # Prevent propagation to root logger to avoid duplicate messages
        logger.propagate = False

    # Cache the logger
    _loggers[name] = logger

    return logger


# =============================================================================
# Convenience Functions
# =============================================================================

def log_exception(
    context: str,
    exc: Exception,
    level: str = 'warning',
    logger_name: str = 'fiberq'
) -> None:
    """
    Quick helper to log an exception with context.

    Args:
        context: Description of what was being attempted
        exc: The exception that was caught
        level: Log level ('debug', 'info', 'warning', 'error', 'critical')
        logger_name: Name of the logger to use

    Example:
        try:
            layer.setName(new_name)
        except Exception as e:
            log_exception("Failed to rename layer", e)
    """
    logger = get_logger(logger_name)
    log_func = getattr(logger, level.lower(), logger.warning)
    log_func(f"{context}: {type(exc).__name__}: {exc}")


def log_warning(message: str, logger_name: str = 'fiberq') -> None:
    """Quick helper to log a warning message."""
    get_logger(logger_name).warning(message)


def log_error(message: str, logger_name: str = 'fiberq', exc_info: bool = False) -> None:
    """Quick helper to log an error message."""
    get_logger(logger_name).error(message, exc_info=exc_info)


def log_debug(message: str, logger_name: str = 'fiberq') -> None:
    """Quick helper to log a debug message."""
    get_logger(logger_name).debug(message)


def log_info(message: str, logger_name: str = 'fiberq') -> None:
    """Quick helper to log an info message."""
    get_logger(logger_name).info(message)


# =============================================================================
# Configuration Helpers
# =============================================================================

def set_log_level(level: str) -> None:
    """
    Dynamically change the log level for all FiberQ loggers.

    Args:
        level: One of 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    """
    numeric_level = getattr(logging, level.upper(), logging.WARNING)

    for logger in _loggers.values():
        logger.setLevel(numeric_level)
        for handler in logger.handlers:
            handler.setLevel(numeric_level)


def get_log_file_path() -> Optional[Path]:
    """
    Get the path to the log file if file logging is enabled.

    Returns:
        Path to log file, or None if file logging is disabled
    """
    if LOG_TO_FILE:
        return LOG_FILE_PATH
    return None


def is_debug_enabled() -> bool:
    """Check if debug logging is enabled."""
    return LOG_LEVEL == 'DEBUG'


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Main logger function
    'get_logger',

    # Convenience functions
    'log_exception',
    'log_warning',
    'log_error',
    'log_debug',
    'log_info',

    # Configuration
    'set_log_level',
    'get_log_file_path',
    'is_debug_enabled',

    # Handler class (for advanced use)
    'QgsLogHandler',

    # Constants
    'LOG_LEVEL',
    'LOG_TO_FILE',
    'LOG_FILE_PATH',
    'PLUGIN_NAME',
]
