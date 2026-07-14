"""FiberQ project schema-version marker (WP1a).

Reads and writes the project ``SCHEMA_VERSION`` to a durable ``QgsProject`` entry
so it survives a normal project save/reopen (QGIS serialises project entries into
the ``.qgs``/``.qgz`` file). The version is also mirrored into the GeoPackage
``_fiberq_metadata`` table on export (see ``ExportManager``) so it travels with
the data file.

Projects created before this marker existed read back as the baseline version
``"0"``. The migration framework (WP1b) is responsible for detecting an old
version on load, upgrading, and stamping the current one.

The marker value comes from the single source of truth,
``fiberq.models.schema.SCHEMA_VERSION``; it is tracked separately from the plugin
version in ``metadata.txt``.
"""
from qgis.core import QgsProject

from ..models.schema import SCHEMA_VERSION
from ..utils.logger import get_logger

logger = get_logger(__name__)

#: QgsProject entry scope (current branding; matches other FiberQPlugin entries).
SCHEMA_VERSION_SCOPE = "FiberQPlugin"
#: QgsProject entry key for the schema version.
SCHEMA_VERSION_KEY = "schema/schema_version"
#: Version reported for projects that predate the marker.
BASELINE_VERSION = "0"


def _project(project=None):
    return project if project is not None else QgsProject.instance()


def read_project_schema_version(project=None) -> str:
    """Return the project's stored schema version, or ``BASELINE_VERSION`` if absent."""
    prj = _project(project)
    try:
        value, ok = prj.readEntry(SCHEMA_VERSION_SCOPE, SCHEMA_VERSION_KEY, "")
        if ok and value:
            return value
    except Exception as e:
        logger.debug(f"read_project_schema_version failed: {e}")
    return BASELINE_VERSION


def write_project_schema_version(version, project=None) -> bool:
    """Write an explicit schema version into the project entry. Returns success."""
    prj = _project(project)
    try:
        return bool(prj.writeEntry(SCHEMA_VERSION_SCOPE, SCHEMA_VERSION_KEY, str(version)))
    except Exception as e:
        logger.debug(f"write_project_schema_version failed: {e}")
        return False


def mark_project_current(project=None) -> bool:
    """Stamp the project with the current ``SCHEMA_VERSION``. Returns success."""
    return write_project_schema_version(SCHEMA_VERSION, project)


def needs_upgrade(project=None) -> bool:
    """True if the project's schema version differs from the current one."""
    return read_project_schema_version(project) != SCHEMA_VERSION
